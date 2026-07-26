# backend/app/cargas/flujo_deudas.py
"""Import del Excel curado 'Flujo de pagos deudas' → MovimientoBancario.

Fuente: hojas `Base real egresos` (Fecha|Descripción|Categoría|Valor|Mes|ID banco) y
`Base real ingresos` (sin Categoría). A diferencia del extracto bancario, la
clasificación YA viene hecha por el CEO — este parser NO clasifica: transforma y
valida (regla 7). Fila con fecha/valor inválido = error reportado, jamás adivinado.
La categoría se resuelve a rubro con `resolver_rubro_id` (fail-loud si no mapea).

Devuelve `MovimientoBancario` (mismo DTO del parser bancario) para reusar
`movimiento_a_transaccion`: id_banco = ID nativo de Global66 (`ID banco`) cuando
existe, o huella determinista del contenido cuando no (regla 5, idempotente).
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from beanie import PydanticObjectId

from app.domain.bancos import Banco
from app.domain.rubro import TipoFlujo
from app.parsers.bank_parsers import MovimientoBancario, TipoMovimiento

_TIPO_MOV = {
    TipoFlujo.EGRESO: TipoMovimiento.DEBITO,
    TipoFlujo.INGRESO: TipoMovimiento.CREDITO,
}


class FilaFlujoError(Exception):
    """Fila que no se pudo transformar sin adivinar (regla 7)."""


def _a_fecha(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    raise FilaFlujoError(f"fecha inválida: {v!r}")


def _a_decimal(v) -> Decimal:
    if v is None or (isinstance(v, str) and v.strip() == ""):
        raise FilaFlujoError("valor vacío")
    if isinstance(v, bool):
        raise FilaFlujoError(f"valor booleano inválido: {v!r}")
    if isinstance(v, (int, float, Decimal)):
        return abs(Decimal(str(v)))
    s = str(v).strip().replace("$", "").replace(" ", "").replace(",", "")
    try:
        return abs(Decimal(s))
    except InvalidOperation:
        raise FilaFlujoError(f"valor no numérico: {v!r}") from None


def parse_fila_flujo(raw: dict, *, tipo_flujo: TipoFlujo) -> MovimientoBancario:
    """Transforma una fila del Excel curado en un MovimientoBancario Global66.
    `raw`: fecha, descripcion, valor, id_banco (opcional). No clasifica."""
    fecha = _a_fecha(raw.get("fecha"))
    monto = _a_decimal(raw.get("valor"))
    if monto == 0:
        raise FilaFlujoError("valor cero (no es movimiento de caja)")
    idb = raw.get("id_banco")
    referencia = str(idb).strip() if idb not in (None, "") else None
    return MovimientoBancario(
        fecha=fecha,
        descripcion=str(raw.get("descripcion") or "").strip(),
        monto=monto,
        tipo=_TIPO_MOV[tipo_flujo],
        banco=Banco.GLOBAL66,
        moneda_original="COP",
        tasa_cambio=Decimal("1"),
        referencia=referencia,
    )


def resolver_rubro_id(
    categoria: str, mapa: dict[str, PydanticObjectId]
) -> PydanticObjectId:
    """Categoría → rubro_id. Fail-loud (regla 7): categoría sin rubro = error, jamás
    se imputa a un rubro adivinado."""
    rid = mapa.get(str(categoria).strip())
    if rid is None:
        raise FilaFlujoError(f"categoría sin rubro en el plan: {categoria!r}")
    return rid
