# backend/app/domain/parametros_proyeccion.py
"""ParametrosProyeccion (COCK-02, CR-COCK) — drivers editables del motor de proyección
(réplica de la hoja PARAMETROS del SIMULADOR). Versionado por `vigente_desde` (como
Configuracion): cada edición crea/actualiza una fila por fecha; el motor usa la vigente.

Captura MANUAL en Fase 1 (Blueprint §1): el CEO carga sus cifras en la app; el armazón
no necesita datos para construirse. Todo monto es Decimal/Money (regla 1). Los
porcentajes (mora/recuperación/default/provisión, tasas) son fracciones (0.03 = 3%).
Los multiplicadores por escenario NO viven aquí: el escenario se pasa al motor y
selecciona los presets (`PRESETS_ESCENARIO`), que el usuario puede sobrescribir.
"""

import re
from datetime import datetime
from decimal import Decimal

from beanie import Document
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pymongo import IndexModel

from app.core.money import Money

PARAMETROS_PROYECCION_COLLECTION = "parametros_proyeccion"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")  # FIX-L: clave de rampa_unidades


class ComponenteAlistamiento(BaseModel):
    """CR-002: un componente del costo de alistamiento por moto vendida
    (matrícula-trámite, instalación GPS, SOAT, …). Configurable desde el editor;
    el motor recibe UN solo Decimal = Σ de los activos (motor.py intacto)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=80)
    valor: Money
    activo: bool = True
    orden: int = 0


def costo_alistamiento_total(
    componentes: list[ComponenteAlistamiento] | None, costo_plano: Decimal
) -> Decimal:
    """La autoridad del CR-002: con componentes, el costo ES la Σ de los activos;
    sin componentes (None/[]), manda el costo plano (compatibilidad)."""
    if not componentes:
        return costo_plano
    total = Decimal("0")
    for c in componentes:
        if c.activo:
            total += c.valor
    return total


class ParametrosProyeccion(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    vigente_desde: str  # 'YYYY-MM-DD' (día 1 del mes normalmente)
    # caja
    caja_inicial: Money
    caja_minima: Money  # el UMBRAL del norte
    # colocación
    motos_base: int = Field(ge=0)
    crec_pct_mensual: Money  # fracción mensual encadenada
    horizonte_meses: int = Field(gt=0, le=180)  # tope 15 años
    # FIX-L: rampa de colocación REAL por mes (YYYY-MM → unidades enteras ≥0). Aditivo:
    # {} → sin rampa (comportamiento de hoy). El servicio la mapea al `rampa` nativo del
    # motor (prefijo contiguo desde mes_inicio; el post-rampa reinicia en motos_base).
    rampa_unidades: dict[str, int] = Field(default_factory=dict)
    # SUP-1 (CEO 2026-08-17): SEGUNDO TRAMO de crecimiento. Una tasa mensual alta es
    # razonable al arrancar pero irreal a 10 años compuesta; el CEO fija desde qué mes
    # el crecimiento baja. `crec_mes_corte = 18` → meses 1..18 con `crec_pct_mensual`,
    # del 19 en adelante con `crec_pct_mensual_2`. Van JUNTOS (fail-closed) y ambos
    # None = comportamiento histórico exacto.
    crec_pct_mensual_2: Money | None = None
    crec_mes_corte: int | None = Field(default=None, gt=0, le=180)
    # inventario Auteco
    adelanto_auteco: Money
    plazo_auteco_dias: int = Field(ge=0)
    base_auteco_dias: int = Field(ge=0)
    tasa_auteco: Money
    # opex
    gastos_fijos: Money
    gps_moto: Money
    # CR-002: "Costos de alistamiento por moto vendida". Si hay componentes, este
    # campo se mantiene = Σ activos (derivado server-side, para lectura coherente).
    costo_moto_nueva: Money
    componentes_alistamiento: list[ComponenteAlistamiento] | None = None
    # deuda inversores
    deuda: Money
    tasa_deuda: Money
    mes_inicio_deuda: int = Field(ge=0)
    meses_deuda: int = Field(ge=0)
    # cartera (mora/default/provisión — valores base del escenario)
    pct_mora: Money
    pct_recuperacion: Money
    pct_default: Money
    pct_provision: Money
    # SUP-2 (CEO 2026-08-22): "TODOS los supuestos que pueden afectar la proyección
    # tienen que ser modificables". Mora/recuperación de los escenarios EXTREMOS (el
    # base son los dos campos de arriba): dejan de vivir en PRESETS_ESCENARIO. None =
    # se conserva el delta en puntos de SUP-1 sobre el preset (compatibilidad).
    pct_mora_pesimista: Money | None = None
    pct_recuperacion_pesimista: Money | None = None
    pct_mora_optimista: Money | None = None
    pct_recuperacion_optimista: Money | None = None
    # Meses de rezago de la recuperación de mora (v9.1 recupera la del mes anterior:
    # la mora es diferimiento, no pérdida). 0 = la semántica del artefacto.
    meses_rezago_recuperacion: int = Field(default=1, ge=0, le=12)
    # Fracción del pago de IVA que se prefondea mes a mes (1 = 100 %, como hasta hoy).
    pct_prefondeo_iva: Money = Decimal("1")
    # Fondo AVAL propio / autoseguro: % del recaudo de crédito reservado cada mes.
    pct_aval_recaudo: Money = Decimal("0")
    modificado_por: str | None = None

    class Settings:
        name = PARAMETROS_PROYECCION_COLLECTION
        # Historial temporal: una fila por vigencia (como Configuracion).
        indexes = [
            IndexModel([("vigente_desde", 1)], name="vigencia_unica", unique=True)
        ]

    @field_validator("rampa_unidades")
    @classmethod
    def _rampa(cls, v: dict[str, int]) -> dict[str, int]:
        for mes, unidades in v.items():
            if not _MES.match(mes):
                raise ValueError(f"rampa_unidades: mes inválido '{mes}' (usa YYYY-MM)")
            if unidades < 0:
                raise ValueError(f"rampa_unidades: unidades negativas en {mes}")
        return v

    @model_validator(mode="after")
    def _pcts_editables_en_rango(self) -> "ParametrosProyeccion":
        """SUP-2: una mora, recuperación, prefondeo o aval fuera de [0, 1] no tiene
        sentido financiero — se rechaza al escribir (fail-closed), no se acota en
        silencio."""
        for campo in (
            "pct_mora_pesimista",
            "pct_recuperacion_pesimista",
            "pct_mora_optimista",
            "pct_recuperacion_optimista",
            "pct_prefondeo_iva",
            "pct_aval_recaudo",
        ):
            v = getattr(self, campo)
            if v is not None and not (Decimal("0") <= v <= Decimal("1")):
                raise ValueError(f"{campo} debe ser una fracción entre 0 y 1")
        return self

    @model_validator(mode="after")
    def _tramo2_completo(self) -> "ParametrosProyeccion":
        """SUP-1: la tasa del segundo tramo y su mes de corte van JUNTOS — media
        configuración proyectaría en silencio con el tramo 1 (fail-closed)."""
        tiene_tasa = self.crec_pct_mensual_2 is not None
        tiene_corte = self.crec_mes_corte is not None
        if tiene_tasa != tiene_corte:
            raise ValueError(
                "segundo tramo de crecimiento incompleto: crec_pct_mensual_2 y "
                "crec_mes_corte van juntos (o ninguno)"
            )
        return self

    @field_validator("vigente_desde")
    @classmethod
    def _fecha(cls, v: object) -> object:
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("vigente_desde debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha inválida: {v}") from e
        return v
