# backend/tests/test_cierre_orden.py
"""FIX-J: guarda de ORDEN de cierre (aditiva). No se puede cerrar un mes cuyo
predecesor inmediato siga EN EJECUCIÓN (quedaría irrecuperable: su sucesor se cerró
y re-ancló). Un predecesor en sugerido/propuesto/definido (borrador nunca iniciado,
como mar–jun en PROD) NO bloquea.

Estos tests corren con mongomock: la guarda dispara ANTES de la transacción, así que
no requieren replica set. El cierre completo (que sí necesita transacción) vive en
test_cierre_realmongo.py.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.cierre.service import CierreError, confirmar_cierre
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from beanie import PydanticObjectId, init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


async def _mes(mes: str, estado: EstadoMes) -> MesControl:
    mc = MesControl(mes=mes, saldo_inicial_caja=Decimal("0"), estado=estado)
    await mc.insert()
    return mc


async def test_cerrar_con_predecesor_en_ejecucion_es_409_orden(db):
    # (a) agosto en ejecución con julio TAMBIÉN en ejecución → cerrar agosto bloquea.
    await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
    await _mes("2026-08-01", EstadoMes.EN_EJECUCION)
    with pytest.raises(CierreError) as exc:
        await confirmar_cierre(mes="2026-08-01", usuario_id=str(PydanticObjectId()))
    assert exc.value.status == 409
    assert "orden" in exc.value.detalle.lower()
    assert "2026-07" in exc.value.detalle


async def test_predecesor_en_sugerido_no_bloquea(db):
    # (b) julio en ejecución con junio en SUGERIDO (borrador nunca iniciado, el caso
    # real de PROD) → la guarda de orden NO dispara. Se pasa de largo hacia el resto
    # del flujo (aquí falla más adelante por falta de siguiente/rubros, no por orden).
    await _mes("2026-06-01", EstadoMes.SUGERIDO)
    await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
    with pytest.raises(CierreError) as exc:
        await confirmar_cierre(mes="2026-07-01", usuario_id=str(PydanticObjectId()))
    # NO es el 409 de orden: el predecesor en sugerido no bloquea.
    assert "orden" not in exc.value.detalle.lower()


async def test_sin_predecesor_no_bloquea(db):
    # Sin MesControl anterior (primer mes de la historia) → la guarda no aplica.
    await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
    with pytest.raises(CierreError) as exc:
        await confirmar_cierre(mes="2026-07-01", usuario_id=str(PydanticObjectId()))
    assert "orden" not in exc.value.detalle.lower()
