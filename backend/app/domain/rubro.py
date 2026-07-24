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
    # Orden = jerarquía del plan de cuentas (ARQUITECTURA_PRESUPUESTAL.md):
    # 0000 ingresos, 1000 costo producto, 2000 operación, 3000 nómina,
    # 4000 deudas, 5000 otros. Ingresos PRIMERO (código 0000).
    INGRESOS_OPERATIVOS = "ingresos_operativos"
    COSTO_PRODUCTO = "costo_producto"
    OPERACION = "operacion"
    NOMINA = "nomina"
    DEUDAS_OBLIGACIONES = "deudas_obligaciones"
    OTROS = "otros"


class TipoFlujo(StrEnum):
    EGRESO = "egreso"
    INGRESO = "ingreso"


class TipoRubro(StrEnum):
    """Rigor del gasto (ARQUITECTURA_PRESUPUESTAL.md): Fijo = piso estructural
    (nómina, arriendos, deuda); Variable = discrecional/operativo. Los rubros de
    sistema pueden no tener tipo (None)."""

    FIJO = "fijo"
    VARIABLE = "variable"


class Rubro(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    grupo: RubroGrupo
    nombre: str = Field(max_length=80)
    tipo_flujo: TipoFlujo = TipoFlujo.EGRESO
    codigo: str | None = Field(default=None, max_length=8)  # jerárquico (p. ej. '2070')
    tipo: TipoRubro | None = None  # Fijo/Variable (None en sistema/no aplica)
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

    @field_validator("tipo", mode="before")
    @classmethod
    def _cast_tipo_rubro(cls, v: object) -> object:
        if v is None or isinstance(v, TipoRubro):
            return v
        return TipoRubro(v)


def _seed() -> list[dict]:
    """Plan de cuentas de ARQUITECTURA_PRESUPUESTAL.md (estructura del archivo de
    Arquitectura + taxonomía real de 'Base real egresos'/'Proyeccion ingresos').

    Cada fila trae `codigo` (jerárquico), `tipo` (Fijo/Variable) y `naturaleza`
    (tipo_flujo). `orden` sigue el código. Rubros de sistema (es_sistema=True):
    'Recaudo de cartera' (0110, destino INGRESO de la regla 'Abono' de C3),
    'Por clasificar' (5070) y 'Ajuste de conciliación' (cierre §2.2.6)."""
    F, V = TipoRubro.FIJO.value, TipoRubro.VARIABLE.value
    ING, EGR = TipoFlujo.INGRESO.value, TipoFlujo.EGRESO.value
    G = RubroGrupo
    # (grupo, [(codigo, nombre, tipo, naturaleza, es_sistema)])
    plan: list[tuple[RubroGrupo, list[tuple]]] = [
        (
            G.INGRESOS_OPERATIVOS,
            [
                ("0110", "Recaudo de cartera", V, ING, True),
                ("0120", "Cuotas iniciales", V, ING, False),
                ("0130", "RODANTE (crédito de repuestos)", V, ING, False),
                ("0140", "Otros ingresos", V, ING, False),
            ],
        ),
        (
            G.COSTO_PRODUCTO,
            [
                ("1010", "Producto", V, EGR, False),
                ("1020", "SOAT/Matrículas", V, EGR, False),
                ("1030", "Seguros (Hunter)", V, EGR, False),
            ],
        ),
        (
            G.OPERACION,
            [
                ("2010", "Arriendos", F, EGR, False),
                ("2020", "Tecnología y software", F, EGR, False),
                ("2030", "Mobiliario/planta/equipo", V, EGR, False),
                ("2040", "Servicios públicos y telecom", F, EGR, False),
                ("2050", "Mercado y aseo", V, EGR, False),
                ("2060", "Cafetería", V, EGR, False),
                ("2070", "Transporte/peajes/combustible/parqueo", V, EGR, False),
                ("2080", "Papelería", V, EGR, False),
                ("2090", "Marketing y publicidad", V, EGR, False),
                ("2100", "Gastos de representación", V, EGR, False),
                ("2110", "Viajes corporativos", V, EGR, False),
                ("2120", "Renting", F, EGR, False),
                ("2130", "Grúas y traslados", V, EGR, False),
                ("2140", "Freelance", V, EGR, False),
            ],
        ),
        (
            G.NOMINA,
            [
                ("3010", "Sueldos empleados", F, EGR, False),
                ("3020", "Sueldos directivos", F, EGR, False),
                ("3030", "Bonificaciones", V, EGR, False),
                ("3040", "Beneficios Heads", V, EGR, False),
                ("3050", "Dotación empleados", V, EGR, False),
                ("3060", "Planillas nuevas", V, EGR, False),
                ("3070", "Planillas anteriores", V, EGR, False),
            ],
        ),
        (
            G.DEUDAS_OBLIGACIONES,
            [
                ("4010", "Préstamos", F, EGR, False),
                ("4020", "Deudas tarjetas de crédito", F, EGR, False),
                ("4030", "Garantía cupo (Auteco)", F, EGR, False),
                ("4040", "Deudas impuestos", F, EGR, False),
                ("4050", "Deudas proveedores anteriores", F, EGR, False),
                ("4060", "Inventario Auteco (150 días)", V, EGR, False),
            ],
        ),
        (
            G.OTROS,
            [
                ("5010", "Otros gastos", V, EGR, False),
                ("5020", "Gastos notariales", V, EGR, False),
                ("5030", "Asuntos legales", F, EGR, False),
                ("5040", "Gastos bancarios", F, EGR, False),
                ("5050", "Gastos financieros", V, EGR, False),
                ("5060", "Impuestos", F, EGR, False),
                ("5070", "Por clasificar", V, EGR, True),
            ],
        ),
    ]
    filas: list[dict] = []
    orden = 0
    for grupo, rubros in plan:
        for codigo, nombre, tipo, naturaleza, sistema in rubros:
            orden += 1
            filas.append(
                {
                    "grupo": grupo.value,
                    "nombre": nombre,
                    "tipo_flujo": naturaleza,
                    "codigo": codigo,
                    "tipo": tipo,
                    "orden": orden,
                    "activo": True,
                    "es_sistema": sistema,
                }
            )
    # 'Ajuste de conciliación' (Spec §2.2.6): rubro de sistema del cierre; no está en
    # el plan de cuentas del negocio (sin código de gasto). Va al final.
    orden += 1
    filas.append(
        {
            "grupo": G.OTROS.value,
            "nombre": "Ajuste de conciliación",
            "tipo_flujo": EGR,
            "codigo": None,
            "tipo": None,
            "orden": orden,
            "activo": True,
            "es_sistema": True,
        }
    )
    return filas


SEMILLA_RUBROS: list[dict] = _seed()
