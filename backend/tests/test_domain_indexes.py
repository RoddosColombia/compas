# backend/tests/test_domain_indexes.py
"""Unicidad de índices — SOLO contra Mongo REAL (mongomock no la exige).

Correr con:  pytest -m requires_real_mongo  (COMPAS_TEST_MONGO_URI apuntando a
un mongod real). En CI de la Sesión 3 (prerrequisito duro del Gate G1)."""

import os
from decimal import Decimal

import pytest
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.factura import Factura
from app.domain.rubro import Rubro
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

pytestmark = pytest.mark.requires_real_mongo


@pytest.fixture
async def real_db():
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    dbname = "compas_test_idx"
    await client.drop_database(dbname)
    database = client[dbname]
    await init_beanie(database=database, document_models=DOMAIN_DOCUMENTS)
    yield database
    await client.drop_database(dbname)
    client.close()


async def test_rubro_nombre_unico_por_grupo(real_db):
    await Rubro(grupo="operacion", nombre="Arriendos", orden=1).insert()
    with pytest.raises(DuplicateKeyError):
        await Rubro(grupo="operacion", nombre="Arriendos", orden=2).insert()


async def test_mismo_nombre_distinto_grupo_ok(real_db):
    await Rubro(grupo="operacion", nombre="Impuestos", orden=1).insert()
    await Rubro(grupo="otros", nombre="Impuestos", orden=2).insert()  # no colisiona


async def test_regla_patron_activo_unico_parcial(real_db):
    # C3 (regla 7): dos reglas ACTIVAS con mismo (patron_normalizado, tipo_flujo)
    # → DuplicateKeyError; una DESACTIVADA no cuenta (índice PARCIAL activa=true).
    from app.domain.regla_clasificacion import ReglaClasificacion
    from beanie import PydanticObjectId

    rid = PydanticObjectId()
    inactiva = ReglaClasificacion(
        patron="Café",
        rubro_id=rid,
        tipo_flujo="egreso",
        prioridad=1,
        activa=False,
        creada_por="u",
    )
    await inactiva.insert()
    activa = ReglaClasificacion(
        patron="cafe",  # mismo normalizado que 'Café'
        rubro_id=rid,
        tipo_flujo="egreso",
        prioridad=2,
        creada_por="u",
    )
    await activa.insert()  # la inactiva NO bloquea
    with pytest.raises(DuplicateKeyError):
        await ReglaClasificacion(
            patron="CAFÉ",
            rubro_id=rid,
            tipo_flujo="egreso",
            prioridad=3,
            creada_por="u",
        ).insert()  # segunda ACTIVA idéntica → colisión


def _factura(**over) -> Factura:
    base = dict(
        tipo="compra",
        origen="otra_compra",
        numero="F1",
        tercero_nombre="Proveedor",
        tercero_nit="900",
        fecha="2026-05-28",
        base_gravable=Decimal("1000.00"),
        tarifa_iva=Decimal("0.19"),
        iva_valor=Decimal("190.00"),
        total=Decimal("1190.00"),
    )
    base.update(over)
    return Factura(**base)


async def test_cufe_unico_sparse_en_mongo_real(real_db):
    """E2/A2: el índice cufe_unico (creado en la migración, NO en Settings) impide dos
    facturas con el mismo CUFE, pero admite VARIAS capturas manuales sin CUFE
    (partialFilterExpression $type:string). Se crea aquí igual que en la migración."""
    await real_db["facturas"].create_index(
        [("cufe", 1)],
        name="cufe_unico",
        unique=True,
        partialFilterExpression={"cufe": {"$type": "string"}},
    )
    cufe = "fabdb194877f049b698d92065704f28fec96e9c0abcd"
    await _factura(cufe=cufe, numero="F1", tercero_nit="900").insert()
    with pytest.raises(DuplicateKeyError):
        await _factura(cufe=cufe, numero="F2", tercero_nit="901").insert()

    # dos capturas MANUALES (cufe=None) NO colisionan: el partial las excluye del índice
    await _factura(cufe=None, numero="M1", tercero_nit="902").insert()
    await _factura(cufe=None, numero="M2", tercero_nit="903").insert()


async def test_configuracion_clave_vigencia_unica(real_db):
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    ).insert()
    with pytest.raises(DuplicateKeyError):
        await Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=Decimal("60000"),
            vigente_desde="2026-01-01",
        ).insert()
