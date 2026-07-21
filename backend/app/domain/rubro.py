# backend/app/domain/rubro.py
"""Rubro (Spec §1.2) + semilla real del Excel congelado.

La semilla NO es de juguete: sale de `Flujo de pagos deudas.xlsx` (hoja
'Presupuesto', fuente de verdad del negocio, PRD M1). Son las 31 categorías reales
de RODDOS agrupadas en los 5 grupos + 2 rubros de sistema que no viven en el Excel:
'Ajuste de conciliación' (cierre de mes, Spec §2.2.6) y 'Recaudo' (tipo INGRESO,
Kimi B-1/S0B-05: destino de los abonos de cuotas, PRD M7). En total 33 rubros;
3 de sistema ('Por clasificar', 'Ajuste de conciliación', 'Recaudo'), inmutables.
"""

from enum import StrEnum

from beanie import Document
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

RUBROS_COLLECTION = "rubros"


class RubroGrupo(StrEnum):
    COSTO_PRODUCTO = "costo_producto"
    OPERACION = "operacion"
    NOMINA = "nomina"
    DEUDAS_OBLIGACIONES = "deudas_obligaciones"
    OTROS = "otros"


class TipoFlujo(StrEnum):
    EGRESO = "egreso"
    INGRESO = "ingreso"


class Rubro(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    grupo: RubroGrupo
    nombre: str = Field(max_length=80)
    tipo_flujo: TipoFlujo = TipoFlujo.EGRESO
    orden: int
    activo: bool = True
    es_sistema: bool = False

    class Settings:
        name = RUBROS_COLLECTION
        # Único por grupo (Spec §1.2). En Mongo real lanza DuplicateKeyError;
        # mongomock no lo exige → se prueba con @requires_real_mongo.
        indexes = [
            IndexModel(
                [("grupo", 1), ("nombre", 1)], name="grupo_nombre_unico", unique=True
            ),
            IndexModel([("orden", 1)], name="por_orden"),
        ]

    @field_validator("grupo", mode="before")
    @classmethod
    def _cast_grupo(cls, v: object) -> object:
        return v if isinstance(v, RubroGrupo) else RubroGrupo(v)

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)


def _seed() -> list[dict]:
    """Catálogo real en el orden de la vista Control del Excel; `orden` global 1..32."""
    G = RubroGrupo
    por_grupo: list[tuple[RubroGrupo, list[str]]] = [
        (G.COSTO_PRODUCTO, ["Producto", "SOAT/Matrículas", "Seguros (Hunter)"]),
        (
            G.OPERACION,
            [
                "Arriendos",
                "Tecnología y software",
                "Mobiliario/planta/equipo",
                "Servicios públicos y telecom",
                "Mercado y aseo",
                "Cafetería",
                "Transporte/peajes/combustible/parqueo",
                "Papelería",
                "Marketing y publicidad",
                "Gastos de representación",
                "Renting",
            ],
        ),
        (
            G.NOMINA,
            [
                "Sueldos empleados",
                "Sueldos directivos",
                "Bonificaciones",
                "Beneficios Heads",
                "Planillas nuevas",
                "Planillas anteriores",
            ],
        ),
        (
            G.DEUDAS_OBLIGACIONES,
            [
                "Préstamos",
                "Deudas tarjetas de crédito",
                "Garantía cupo",
                "Deudas impuestos",
                "Deudas proveedores anteriores",
            ],
        ),
        (
            G.OTROS,
            [
                "Otros gastos",
                "Gastos notariales",
                "Gastos bancarios",
                "Gastos financieros",
                "Impuestos",
                "Por clasificar",  # de sistema (Spec §1.2)
            ],
        ),
    ]
    sistema = {"Por clasificar"}
    filas: list[dict] = []
    orden = 0
    for grupo, nombres in por_grupo:
        for nombre in nombres:
            orden += 1
            filas.append(
                {
                    "grupo": grupo.value,
                    "nombre": nombre,
                    "tipo_flujo": "egreso",
                    "orden": orden,
                    "activo": True,
                    "es_sistema": nombre in sistema,
                }
            )
    # 'Ajuste de conciliación': de sistema, exigido por el cierre (Spec §2.2.6);
    # no vive en el Excel. Grupo 'otros'.
    orden += 1
    filas.append(
        {
            "grupo": G.OTROS.value,
            "nombre": "Ajuste de conciliación",
            "tipo_flujo": "egreso",
            "orden": orden,
            "activo": True,
            "es_sistema": True,
        }
    )
    # 'Recaudo': de sistema, tipo INGRESO (Kimi B-1 / S0B-05). Destino de los
    # abonos de cuotas (regla PRD M7 'Abono' → ingreso recaudo); sin él, la
    # clasificación automática de ingresos no tiene rubro. Tampoco vive en el Excel.
    orden += 1
    filas.append(
        {
            "grupo": G.OTROS.value,
            "nombre": "Recaudo",
            "tipo_flujo": "ingreso",
            "orden": orden,
            "activo": True,
            "es_sistema": True,
        }
    )
    return filas


SEMILLA_RUBROS: list[dict] = _seed()
