# backend/app/domain/factura.py
"""Factura (C11, PR-2a "Fidelidad de caja") — una factura de compra o venta cargada
para liquidar el IVA cuatrimestral y restar el IVA neto de la caja en la fecha DIAN.

NO es un movimiento bancario (eso es `Transaccion`): es el insumo del liquidador de
IVA. `iva_valor`/`total` los calcula el backend desde `base_gravable`×`tarifa_iva`
(regla 1: todo cálculo de dinero en el backend). Baja LÓGICA (`activo`): una factura
mal cargada se anula, no se borra (regla 4 / auditoría). Dedup (regla 5): índice único
parcial (tercero_nit, numero) — el par NIT+número es el identificador natural de una
factura; dos proveedores con el mismo número NO colisionan. Cuatrimestre = DERIVADO de
`fecha` (no se persiste; lo calcula `iva.liquidacion.periodo_de` según la periodicidad).

Auteco (NIT 860024781) es autorretenedor: su IVA SÍ es descontable (`deducible=True`),
pero NUNCA se le aplica ReteFuente (regla de contabilidad RODDOS). CUATRIMESTRAL 19%.
"""

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from beanie import Document
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money

FACTURAS_COLLECTION = "facturas"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Único tipo de documento que E2 procesa (D-16: NC/ND/soporte van a E2.1).
TIPO_DOC_FACTURA_VENTA = "FACTURA ELECTRÓNICA DE VENTA"

# Pieza 6 (E2 §3.5): tarifas IVA legales en Colombia — 0% (exento/excluido), 5%
# (reducida) y 19% (general). Lista CERRADA para la captura MANUAL (endurecer, no
# cambiar el cálculo → sin CR por R6). La ingesta DIAN NO valida contra esto: el PDF
# puede mezclar tarifas (trampa 4 del §2) y guarda tarifa_iva=None (manda iva_valor).
TARIFAS_IVA_VALIDAS = frozenset(
    {Decimal("0"), Decimal("0.05"), Decimal("0.19")}
)


class TipoFactura(StrEnum):
    venta = "venta"  # genera IVA (débito fiscal) — 'emitida' en el PDF DIAN
    compra = "compra"  # IVA descontable si es deducible — 'recibida' en el PDF


class OrigenFactura(StrEnum):
    auteco = "auteco"  # compra del lote de motos a Auteco (autorretenedor)
    otra_compra = "otra_compra"
    moto = "moto"  # venta de moto
    repuesto = "repuesto"
    servicio = "servicio"
    otro = "otro"
    # E2: la ingesta NO puede deducir el origen de negocio del PDF (a diferencia del
    # tipo, que sí sale del NIT). Entra 'sin_clasificar' con contador visible; el CEO
    # lo reclasifica. Nunca se adivina (R5).
    sin_clasificar = "sin_clasificar"


class Factura(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    tipo: TipoFactura
    origen: OrigenFactura
    numero: str = Field(min_length=1, max_length=60)
    tercero_nombre: str = Field(min_length=1, max_length=200)
    tercero_nit: str = Field(min_length=1, max_length=30)
    fecha: str  # 'YYYY-MM-DD' (Bogotá); el cuatrimestre se deriva de aquí
    # base GRAVADA (la que causa IVA). Manual: obligatoria. Ingesta DIAN: None —
    # la Representación Gráfica solo trae el "Total Bruto" (que incluye líneas sin
    # IVA), no la base gravada por línea; guardarlo aquí sería fiscalmente falso
    # (tarifa implícita absurda, reportes fiscales errados). R5: no se inventa.
    base_gravable: Money | None
    # Total Bruto Factura de la DIAN (incluye líneas sin IVA). None en captura
    # manual (ahí manda base_gravable). Junto con iva/inc/... cuadra el total (A6).
    total_bruto: Money | None = None
    # fracción (0.19 general, 0 exento) — informativo si viene iva_valor. None
    # SOLO en la ingesta DIAN: una factura puede mezclar tarifas (trampa 4 del
    # §2) y derivar tarifa desde iva/base mete redondeos en un dato fiscal
    # (alternativa rechazada en §3.2); la captura manual la sigue exigiendo.
    tarifa_iva: Money | None
    # E2/D-13: el iva_valor extraído del PDF MANDA; si no, base × tarifa (servicio)
    iva_valor: Money
    # = base_gravable + impuestos (se reutiliza; no se agrega total_factura)
    total: Money
    deducible: bool = False  # solo compras: si su IVA es descontable
    activo: bool = True  # baja lógica (anulación)

    # ── E2: campos de la Representación Gráfica DIAN ──
    cufe: str | None = None  # identificador único DIAN; None en captura manual
    tipo_documento: str = TIPO_DOC_FACTURA_VENTA  # radar E2.1 (NC/ND llevarían otro)
    signo: int = 1  # +1 factura; -1 reservado para notas crédito (E2.1)
    # `inc_valor` y no `inc`: `inc` pisa un atributo de beanie.Document (UserWarning de
    # Pydantic; rompería updates a futuro). Desviación del §3.1 documentada en el PR.
    inc_valor: Money = Decimal("0.00")
    bolsas: Money = Decimal("0.00")
    otros_impuestos: Money = Decimal("0.00")
    rete_fuente: Money = Decimal("0.00")
    rete_iva: Money = Decimal("0.00")
    rete_ica: Money = Decimal("0.00")
    # ref/hash del PDF original (auditable, restringido por rol PII)
    archivo_ref: str | None = None

    class Settings:
        name = FACTURAS_COLLECTION
        indexes = [
            # Regla 5: dedup por el par natural NIT+número. Se conserva porque las
            # capturas MANUALES no tienen CUFE. Único donde numero es string (siempre).
            IndexModel(
                [("tercero_nit", 1), ("numero", 1)],
                name="nit_numero_unico",
                unique=True,
                partialFilterExpression={"numero": {"$type": "string"}},
            ),
            IndexModel([("fecha", 1)], name="por_fecha"),
            # ⚠ El índice único de CUFE (A2) va en la MIGRACIÓN, no aquí. El
            # partialFilterExpression {"cufe": {"$type":"string"}} es correcto en
            # Mongo real (excluye capturas manuales sin CUFE), pero mongomock IGNORA
            # el partial y lo trataría como único simple → dos cufe=None colisionan y
            # rompen la suite rápida. Se crea (cufe_unico) en la migración
            # 20260728_e2_facturas_iva; la dedup CUFE va además en el servicio y se
            # verifica @requires_real_mongo.
        ]

    @field_validator("fecha")
    @classmethod
    def _fecha_str(cls, v: object) -> str:
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("fecha debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha inválida: {v}") from e
        return v

    @field_validator("tipo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFactura) else TipoFactura(v)

    @field_validator("origen", mode="before")
    @classmethod
    def _cast_origen(cls, v: object) -> object:
        return v if isinstance(v, OrigenFactura) else OrigenFactura(v)
