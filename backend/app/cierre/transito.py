# backend/app/cierre/transito.py
"""CR-WAVA §4 — tránsito heredado y remanente (compute-only, nunca se copia).

El tránsito lo declara un mes AL CERRAR (`MesControl.transito_wava`). El mes siguiente
lo hereda de forma DERIVADA:

- `transito_heredado(mes)` = lo declarado por el mes inmediatamente anterior (apertura;
  alimenta `caja_inicial_total` en la lista de meses).
- `transito_remanente(mes)` = lo que aún NO ha aterrizado del último mes cerrado con
  declaración > 0: `max(0, Y − Σ llegadas)`, donde las llegadas son las tx de INGRESO al
  rubro «Tránsito Wava mes anterior» en meses posteriores al que declaró. Rueda hacia
  adelante (un settlement tardío en M+2 sigue descontando) y se clampa en 0 (la
  sobre-llegada es recaudo normal, no tránsito).
"""

from decimal import Decimal

from app.domain.mes_control import EstadoMes, MesControl
from app.domain.regla_clasificacion import normalizar_texto
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion

RUBRO_TRANSITO = "Tránsito Wava mes anterior"

# CR-WAVA-2 (decisión CEO 2026-08-03): patrón real del depósito Wava en Global66.
# Ya normalizados (lower, sin tildes); match por *contains* → cubre
# "Recibido de WAVA Technologie…". Es la ÚNICA vía automática hacia el rubro
# tránsito (que es es_sistema → ninguna ReglaClasificacion puede apuntarle).
PATRONES_TRANSITO: tuple[str, ...] = ("recibido de wava",)


def es_transito_wava(descripcion: str) -> bool:
    """¿La descripción de un movimiento es un depósito Wava? Usa la MISMA
    `normalizar_texto` que el motor de reglas (sin divergencia silenciosa)."""
    norm = normalizar_texto(descripcion)
    return any(p in norm for p in PATRONES_TRANSITO)


class AsignadorTransito:
    """Decide, movimiento a movimiento dentro de UNA corrida (una carga o un
    `aplicar_pendientes`), si un depósito Wava debe clasificarse al rubro tránsito.

    Cache + descuento en batch: calcula `transito_remanente(mes)` una sola vez por
    mes y le resta el valor de cada depósito que manda a tránsito. Así el
    comportamiento dentro de un archivo == cargas secuenciales (el 2º depósito ve el
    remanente ya reducido por el 1º) y nunca sobre-asigna más que lo declarado.
    """

    def __init__(self) -> None:
        self._rem: dict[str, Decimal] = {}

    async def asigna(
        self, *, descripcion: str, mes: str, tipo_flujo: TipoFlujo, valor: Decimal
    ) -> bool:
        """True (→ rubro tránsito, sello de sistema) solo si es INGRESO, matchea el
        patrón Wava y aún hay remanente vivo para `mes`; descuenta el valor."""
        if tipo_flujo is not TipoFlujo.INGRESO:
            return False
        if not es_transito_wava(descripcion):
            return False
        if mes not in self._rem:
            self._rem[mes] = await transito_remanente(mes)
        if self._rem[mes] > 0:
            self._rem[mes] -= valor
            return True
        return False


def _mes_anterior(mes: str) -> str:
    """YYYY-MM-01 del mes inmediatamente anterior."""
    y, m, _ = mes.split("-")
    y, m = int(y), int(m)
    if m == 1:
        return f"{y - 1:04d}-12-01"
    return f"{y:04d}-{m - 1:02d}-01"


async def transito_heredado(mes: str) -> Decimal:
    """Tránsito de apertura = lo declarado por el mes inmediatamente anterior (0 si no
    existe o no declaró). `mes` es YYYY-MM-01."""
    prev = await MesControl.find_one(MesControl.mes == _mes_anterior(mes))
    return prev.transito_wava if prev is not None else Decimal("0")


async def _mc_prev_con_transito(mes: str) -> MesControl | None:
    """Último mes CERRADO estrictamente antes de `mes` con transito_wava > 0."""
    async for mc in MesControl.find(
        MesControl.mes < mes,
        MesControl.estado == EstadoMes.CERRADO,
    ).sort(-MesControl.mes):
        if mc.transito_wava > 0:
            return mc
    return None


async def _suma_llegadas_despues(mes_prev: str) -> Decimal:
    """Σ de las tx de INGRESO al rubro tránsito con fecha en un mes POSTERIOR a
    `mes_prev` (roll-forward: cuenta llegadas de cualquier mes siguiente)."""
    rubro = await Rubro.find_one(Rubro.nombre == RUBRO_TRANSITO)
    if rubro is None:
        return Decimal("0")
    total = Decimal("0")
    async for t in Transaccion.find(
        Transaccion.rubro_id == rubro.id,
        Transaccion.tipo_flujo == TipoFlujo.INGRESO,
    ):
        if t.fecha[:7] > mes_prev[:7]:
            total += t.valor
    return total


async def transito_remanente(mes: str) -> Decimal:
    """Remanente vivo del último mes cerrado con declaración: `max(0, Y − Σ llegadas)`.
    0 si no hay declaración previa."""
    prev = await _mc_prev_con_transito(mes)
    if prev is None:
        return Decimal("0")
    llegadas = await _suma_llegadas_despues(prev.mes)
    remanente = prev.transito_wava - llegadas
    return remanente if remanente > 0 else Decimal("0")


async def aviso_transito(mes: str) -> dict | None:
    """Si al cerrar `mes` sigue habiendo remanente del tránsito declarado en un mes
    anterior, devuelve {declarado, llegado, remanente, mes_declaracion} para el aviso
    informativo del cierre. None si no hay remanente (o no hubo declaración)."""
    prev = await _mc_prev_con_transito(mes)
    if prev is None:
        return None
    llegadas = await _suma_llegadas_despues(prev.mes)
    remanente = prev.transito_wava - llegadas
    if remanente <= 0:
        return None
    return {
        "declarado": prev.transito_wava,
        "llegado": llegadas,
        "remanente": remanente,
        "mes_declaracion": prev.mes[:7],
    }
