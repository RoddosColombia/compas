# backend/app/reglas/semilla_service.py
"""RF-F1 paso 2 — servicio de la semilla (capa Mongo sobre el generador puro).

`proponer_semilla` es LECTURA PURA: lee la curaduría real (transacciones ya clasificadas
por el CEO en rubros no-sistema), corre `generar_reglas_semilla` y arma un reporte
revisable (patrón · rubro · evidencia · pureza · ejemplos reales · si choca con una
regla activa). NO escribe nada — persistir las aprobadas es un paso aparte, con
aprobación del CEO (vía `proponer_regla_aprendida`, que las crea inactivas).

Qué se aprende y qué no:
  · SOLO rubros `es_sistema=False` → excluye «Por clasificar» (la bandeja) y los
    automáticos (Ajuste de conciliación, Tránsito Wava, Recaudo de cartera).
  · Se ignoran transacciones DIVIDIDAS (`partes`): una descripción repartida en varios
    rubros no es señal limpia.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from beanie import PydanticObjectId

from app.domain.regla_clasificacion import (
    PATRON_MIN,
    ReglaClasificacion,
    normalizar_texto,
)
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion
from app.reglas.semilla import (
    STOPWORDS_DEFAULT,
    MovimientoClasificado,
    generar_reglas_semilla,
    tokens_de,
)
from app.reglas.service import (
    ReglasError,
    _patron_activo_duplicado,
    proponer_regla_aprendida,
)


async def proponer_semilla(
    *,
    min_evidencia: int = 3,
    min_pureza: Decimal = Decimal("1"),
    max_ejemplos: int = 3,
) -> dict:
    """Reporte revisable de reglas semilla aprendidas del histórico. LECTURA PURA."""
    rubros: dict = {}
    async for r in Rubro.find(Rubro.es_sistema == False):  # noqa: E712
        rubros[r.id] = r.nombre

    movimientos: list[MovimientoClasificado] = []
    ejemplos: dict[tuple, list[str]] = defaultdict(list)
    async for tx in Transaccion.find(Transaccion.partes == None):  # noqa: E711
        if tx.rubro_id not in rubros:
            continue
        movimientos.append(
            MovimientoClasificado(tx.descripcion, tx.rubro_id, tx.tipo_flujo)
        )
        for token in tokens_de(tx.descripcion):
            muestras = ejemplos[(tx.tipo_flujo, token)]
            if tx.descripcion not in muestras and len(muestras) < max_ejemplos:
                muestras.append(tx.descripcion)

    reglas = generar_reglas_semilla(
        movimientos, min_evidencia=min_evidencia, min_pureza=min_pureza
    )

    propuestas = []
    for regla in reglas:
        colisiona = await _patron_activo_duplicado(regla.patron, regla.tipo_flujo)
        propuestas.append(
            {
                "patron": regla.patron,
                "rubro_id": str(regla.rubro_id),
                "rubro": rubros.get(regla.rubro_id, "?"),
                "tipo_flujo": regla.tipo_flujo.value,
                "evidencia": regla.evidencia,
                "pureza": str(regla.pureza.normalize()),
                "prioridad": regla.prioridad,
                "ejemplos": ejemplos.get((regla.tipo_flujo, regla.patron), []),
                "colisiona": colisiona,
            }
        )

    return {
        "total_movimientos": len(movimientos),
        "parametros": {
            "min_evidencia": min_evidencia,
            "min_pureza": str(min_pureza),
            "min_long_patron": PATRON_MIN,
            "stopwords": len(STOPWORDS_DEFAULT),
        },
        "propuestas": propuestas,
    }


async def _existe_patron(patron: str, tipo: TipoFlujo) -> bool:
    """Idempotencia: ¿ya hay una regla (activa O inactiva) con ese patrón+tipo?"""
    pn = normalizar_texto(patron)
    r = await ReglaClasificacion.find_one(
        ReglaClasificacion.patron_normalizado == pn,
        ReglaClasificacion.tipo_flujo == tipo,
    )
    return r is not None


async def sembrar_semilla(reglas: list[dict], usuario_id: str) -> dict:
    """Persiste las reglas seleccionadas como origen=APRENDIDA e INACTIVAS
    (`proponer_regla_aprendida` → activa=False; exigen aprobación). Idempotente: salta
    los patrones que ya existen. Robusto: un choque (rubro incoherente / duplicado
    activo) se registra en `errores` y NO aborta el lote.

    Cada regla: {patron, rubro_id, tipo_flujo, prioridad?}. Devuelve el conteo."""
    creadas = existentes = 0
    errores: list[dict] = []
    for r in reglas:
        tipo = r["tipo_flujo"]
        if not isinstance(tipo, TipoFlujo):
            tipo = TipoFlujo(tipo)
        if await _existe_patron(r["patron"], tipo):
            existentes += 1
            continue
        try:
            await proponer_regla_aprendida(
                patron=r["patron"],
                rubro_id=PydanticObjectId(r["rubro_id"]),
                tipo_flujo=tipo,
                usuario_id=usuario_id,
                prioridad=int(r.get("prioridad", 100)),
            )
            creadas += 1
        except ReglasError as e:
            errores.append({"patron": r["patron"], "detalle": e.detalle})
    return {
        "creadas": creadas,
        "ya_existian": existentes,
        "errores": len(errores),
        "detalle_errores": errores,
    }
