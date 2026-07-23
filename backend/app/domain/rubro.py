# backend/app/domain/rubro.py
"""Rubro (Spec §1.2) + semilla real de la taxonomía del negocio.

La semilla NO es de juguete: es la taxonomía REAL de `docs/modelo/MODELO.md`
(destilada de la hoja 'Base real egresos' de `Flujo de pagos deudas.xlsx`) — re-seed
C1, GO Kimi PLAN-I 9.2. Son las 31 categorías reales de RODDOS en los 5 grupos + 3
rubros de sistema inmutables: 'Por clasificar' (Spec §1.2), 'Ajuste de conciliación'
(cierre de mes, Spec §2.2.6) y 'Recaudo' (tipo INGRESO, Kimi B-1/S0B-05: destino de
los abonos de cuotas, PRD M7). En total 34 rubros.

D3 (gate C1): las categorías viejas de la semilla anterior que ya existan en la BD
NO se tocan ($setOnInsert) ni se borran — el CEO las depura desde la app (C1). El
re-seed reporta las colisiones (B-4, ver `seed.py::seed_rubros_reporte`).
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
    """Taxonomía real de MODELO.md ('Base real egresos'); `orden` global 1..34.

    Los 3 de sistema viven en 'otros' — MISMA llave (grupo,nombre) que los docs ya
    sembrados en prod: el $setOnInsert los reconoce y no los duplica."""
    G = RubroGrupo
    por_grupo: list[tuple[RubroGrupo, list[str]]] = [
        (G.COSTO_PRODUCTO, ["Producto", "SOAT/Matrículas", "Seguros (Hunter)"]),
        (
            G.OPERACION,
            [
                "Transporte/peajes/combustible/parqueo",
                "Cafetería",
                "Mercado y aseo",
                "Tecnología y software",
                "Gastos de representación",
                "Papelería",
                "Marketing y publicidad",
                "Servicios públicos y telecom",
                "Mobiliario/planta/equipo",
                "Viajes corporativos",
                "Grúas y traslados",
                "Dotación empleados",
                "Freelance",
            ],
        ),
        (
            G.NOMINA,
            [
                "Sueldos directivos",
                "Sueldos empleados",
                "Bonificaciones",
                "Beneficios Heads",
                "Planillas anteriores",
            ],
        ),
        (
            G.DEUDAS_OBLIGACIONES,
            [
                "Préstamos",
                "Deudas proveedores anteriores",
                "Deudas tarjetas de crédito",
            ],
        ),
        (
            G.OTROS,
            [
                "Impuestos",
                "Otros gastos",
                "Gastos bancarios",
                "Gastos financieros",
                "Asuntos legales",
                "Gastos notariales",
                "Arriendos",  # MODELO.md lo ubica en OTROS (antes: operación)
            ],
        ),
    ]
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
                    "es_sistema": False,
                }
            )
    # ── Rubros de sistema (inmutables; no viven en el Excel salvo Por clasificar) ──
    # 'Por clasificar' (Spec §1.2): destino de todo movimiento sin clasificar.
    # 'Ajuste de conciliación' (Spec §2.2.6): exigido por el cierre de mes.
    # 'Recaudo' (Kimi B-1/S0B-05): INGRESO, destino de los abonos de cuotas (PRD M7).
    for nombre, tipo in [
        ("Por clasificar", "egreso"),
        ("Ajuste de conciliación", "egreso"),
        ("Recaudo", "ingreso"),
    ]:
        orden += 1
        filas.append(
            {
                "grupo": G.OTROS.value,
                "nombre": nombre,
                "tipo_flujo": tipo,
                "orden": orden,
                "activo": True,
                "es_sistema": True,
            }
        )
    return filas


SEMILLA_RUBROS: list[dict] = _seed()
