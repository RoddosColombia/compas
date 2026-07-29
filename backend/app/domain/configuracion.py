# backend/app/domain/configuracion.py
"""Configuracion (Spec §1.10): reglas de negocio parametrizables en BD, no en env.

`valor` polimórfico TIPADO POR CLAVE (Kimi M-03): en vez de un `valor` genérico que
rompería 'dinero=Decimal', cada clave declara su tipo esperado y se persiste en el
campo correspondiente (`valor_decimal` COP, `valor_fecha` 'YYYY-MM-DD', `valor_json`).
Exactamente uno de los tres va poblado, y debe coincidir con el tipo de la clave.
"""

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from beanie import Document
from pydantic import ConfigDict, field_validator, model_validator
from pymongo import IndexModel

from app.core.money import Money

CONFIGURACION_COLLECTION = "configuracion"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ClaveConfig(StrEnum):
    UMBRAL_DIF_BANCO_CIERRE = "UMBRAL_DIF_BANCO_CIERRE"
    CALENDARIO_DIAN = "CALENDARIO_DIAN"
    DIAS_CREDITO_POR_PROVEEDOR = "DIAS_CREDITO_POR_PROVEEDOR"
    # Período de liquidación del IVA (decisión CEO 2026-07-25): default cuatrimestral;
    # la DIAN puede pasar a RODDOS a bimestral por volumen → configurable por dato.
    PERIODICIDAD_IVA = "PERIODICIDAD_IVA"
    # E2: NIT propio (RODDOS) y de Auteco a config, no hardcodeados en el extractor.
    NIT_RODDOS = "NIT_RODDOS"
    NIT_AUTECO = "NIT_AUTECO"
    # E2 (CR-E2-COMPUERTA): compuerta IVA→proyección. Apagada por defecto → E2 captura
    # facturas y liquida el IVA SIN mover la caja proyectada (D-12). Encender es dato.
    IVA_ALIMENTA_PROYECCION = "IVA_ALIMENTA_PROYECCION"


# Tipo esperado por clave (M-03). "decimal" | "fecha" | "json".
_TIPO_POR_CLAVE: dict[ClaveConfig, str] = {
    ClaveConfig.UMBRAL_DIF_BANCO_CIERRE: "decimal",
    ClaveConfig.CALENDARIO_DIAN: "json",
    ClaveConfig.DIAS_CREDITO_POR_PROVEEDOR: "json",
    ClaveConfig.PERIODICIDAD_IVA: "json",
    ClaveConfig.NIT_RODDOS: "json",
    ClaveConfig.NIT_AUTECO: "json",
    ClaveConfig.IVA_ALIMENTA_PROYECCION: "json",
}


class Configuracion(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    clave: ClaveConfig
    valor_decimal: Money | None = None
    valor_fecha: str | None = None
    valor_json: dict[str, Any] | None = None
    vigente_desde: str  # 'YYYY-MM-DD'
    modificado_por: str | None = None

    class Settings:
        name = CONFIGURACION_COLLECTION
        # Historial temporal: una fila por (clave, vigente_desde).
        indexes = [
            IndexModel(
                [("clave", 1), ("vigente_desde", 1)],
                name="clave_vigencia_unica",
                unique=True,
            )
        ]

    @field_validator("clave", mode="before")
    @classmethod
    def _cast_clave(cls, v: object) -> object:
        return v if isinstance(v, ClaveConfig) else ClaveConfig(v)

    @field_validator("vigente_desde", "valor_fecha")
    @classmethod
    def _fecha(cls, v: object) -> object:
        if v is None:
            return v
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("fecha debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha inválida: {v}") from e
        return v

    @model_validator(mode="after")
    def _un_solo_valor_del_tipo_correcto(self) -> "Configuracion":
        presentes = {
            "decimal": self.valor_decimal is not None,
            "fecha": self.valor_fecha is not None,
            "json": self.valor_json is not None,
        }
        cuantos = sum(presentes.values())
        if cuantos != 1:
            raise ValueError(
                f"debe poblarse exactamente un valor_* (recibidos: {cuantos})"
            )
        esperado = _TIPO_POR_CLAVE[self.clave]
        if not presentes[esperado]:
            raise ValueError(
                f"la clave {self.clave.value} exige valor_{esperado} (M-03)"
            )
        return self


# --- Semilla real (fechas IVA de RODDOS, NIT 901012622 dígito 2) ---
# ene–abr → 13-may-26 · may–ago → 10-sep-26 · sep–dic → 14-ene-27
SEMILLA_CONFIGURACION: list[dict] = [
    {
        "clave": "UMBRAL_DIF_BANCO_CIERRE",
        "valor_decimal": Decimal("50000"),  # Spec §0.1 (default, editable por Admin)
        "vigente_desde": "2026-01-01",
    },
    {
        "clave": "CALENDARIO_DIAN",
        "valor_json": {
            "2026": {
                "ene_abr": "2026-05-13",
                "may_ago": "2026-09-10",
                "sep_dic": "2027-01-14",
            }
        },
        "vigente_desde": "2026-01-01",
    },
    {
        # Días de crédito por proveedor: dato operativo que administra Financiero;
        # se declara la clave con dict vacío (no se inventan valores).
        "clave": "DIAS_CREDITO_POR_PROVEEDOR",
        "valor_json": {},
        "vigente_desde": "2026-01-01",
    },
    {
        # Período del IVA: hoy CUATRIMESTRAL (realidad RODDOS). El CEO lo cambia a
        # 'bimestral' cuando la DIAN lo exija — sin tocar código (decisión 2026-07-25).
        "clave": "PERIODICIDAD_IVA",
        "valor_json": {"periodicidad": "cuatrimestral"},
        "vigente_desde": "2026-01-01",
    },
    {
        "clave": "NIT_RODDOS",
        "valor_json": {"nit": "901012622"},
        "vigente_desde": "2026-01-01",
    },
    {
        "clave": "NIT_AUTECO",
        "valor_json": {"nit": "860024781"},
        "vigente_desde": "2026-01-01",
    },
    {
        # CR-E2-COMPUERTA: IVA→proyección APAGADA por defecto (D-12). Encender = dato.
        "clave": "IVA_ALIMENTA_PROYECCION",
        "valor_json": {"activa": False},
        "vigente_desde": "2026-01-01",
    },
]
