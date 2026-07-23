# backend/tests/test_pagos_marcar_realmongo.py
"""C9/S5-01 — marcar-pagado contra Mongo REAL (D5 multi-doc + regla 8 + saga O1).

MARCADO PARA AUDITORÍA KIMI.

`marcar-pagado` enlaza el pago a una Transaccion existente en una TRANSACCIÓN
multi-documento (pago→pagado + pagado_tx_id, tx.pago_planeado_id). mongomock no
soporta sesiones → el happy-path, la atomicidad y la saga O1 viven aquí
(@requires_real_mongo, replica set en CI)."""

import os
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.core.time import today_bogota
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.pago_planeado import EstadoPago, PagoPlaneado
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

PWD = "clave-larga-1234"
HOY = today_bogota().isoformat()
EN_SEMANA = (today_bogota() + timedelta(days=2)).isoformat()


@pytest.mark.requires_real_mongo
class TestMarcarPagadoReal:
    @pytest_asyncio.fixture
    async def entorno(self, monkeypatch):
        uri = os.environ.get("COMPAS_TEST_MONGO_URI")
        if not uri:
            pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("JWT_SECRET", "x" * 40)
        monkeypatch.setenv("COOKIE_SECURE", "False")
        monkeypatch.delenv("RUN_SCHEDULER", raising=False)
        get_settings.cache_clear()
        from app.main import create_app

        app = create_app()
        client = AsyncIOMotorClient(uri, tz_aware=True)
        dbname = "compas_test_pagos"
        await client.drop_database(dbname)
        db = client[dbname]
        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
        repository.configure_auth(client, dbname)
        configure_audit(client, dbname)
        await repository.create_user(
            User(
                email="fin@roddos.com",
                password_hash=passwords.hash_password(PWD),
                rol=Role.financiero,
            )
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, db
        repository.reset_auth()
        reset_audit()
        await client.drop_database(dbname)
        client.close()
        get_settings.cache_clear()

    async def _token(self, ac):
        r = await ac.post(
            "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
        )
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    async def _sembrar(self):
        mc = MesControl(
            mes=f"{HOY[:7]}-01",
            saldo_inicial_caja=Decimal("0"),
            estado=EstadoMes.EN_EJECUCION,
        )
        await mc.insert()
        rubro = Rubro(
            grupo="deudas_obligaciones", nombre="Proveedores", orden=50, activo=True
        )
        await rubro.insert()
        pago = PagoPlaneado(
            concepto="Cuota",
            acreedor="Auteco",
            monto=Decimal("100000"),
            fecha_programada=EN_SEMANA,
            rubro_id=rubro.id,
            mes_id=mc.id,
        )
        await pago.insert()
        tx = Transaccion(
            fecha=HOY,
            descripcion="Pago a Auteco",
            valor=Decimal("100000"),
            tipo_flujo="egreso",
            rubro_id=rubro.id,
            mes_id=mc.id,
            banco=Banco.GLOBAL66,
            id_banco="G66-PAGO-1",
        )
        await tx.insert()
        return mc, rubro, pago, tx

    async def test_marcar_pagado_enlaza_ambos_docs(self, entorno):
        ac, _ = entorno
        h = await self._token(ac)
        _, _, pago, tx = await self._sembrar()
        r = await ac.post(
            f"/api/v1/pagos-planeados/{pago.id}/marcar-pagado",
            json={"transaccion_id": str(tx.id)},
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["estado"] == "pagado"
        p = await PagoPlaneado.get(pago.id)
        assert p.estado is EstadoPago.PAGADO
        assert p.pagado_tx_id == tx.id
        t = await Transaccion.get(tx.id)
        assert t.pago_planeado_id == pago.id  # el FK inverso (multi-doc)

    async def test_marcar_pagado_o1_compensa(self, entorno, monkeypatch):
        # commit OK pero el emit cae → se revierte AMBOS docs (pago y tx) y propaga.
        ac, db = entorno
        h = await self._token(ac)
        _, _, pago, tx = await self._sembrar()

        async def _boom(*a, **k):
            raise RuntimeError("audit caído")

        monkeypatch.setattr("app.pagos.service.emit_audit", _boom)
        with pytest.raises(RuntimeError):
            await ac.post(
                f"/api/v1/pagos-planeados/{pago.id}/marcar-pagado",
                json={"transaccion_id": str(tx.id)},
                headers=h,
            )
        monkeypatch.undo()
        p = await PagoPlaneado.get(pago.id)
        assert p.estado is EstadoPago.PENDIENTE  # revertido
        assert p.pagado_tx_id is None
        t = await Transaccion.get(tx.id)
        assert t.pago_planeado_id is None  # revertido
        assert (
            await db["audit_log"].count_documents({"evento": "pago_planeado.editado"})
            == 0
        )

    async def test_marcar_pagado_mes_cerrado_409(self, entorno):
        # regla 4: si el mes se cerró, no se puede marcar pagado (guard antes de la tx)
        ac, _ = entorno
        h = await self._token(ac)
        mc, _, pago, tx = await self._sembrar()
        mc.estado = EstadoMes.CERRADO
        await mc.save()
        r = await ac.post(
            f"/api/v1/pagos-planeados/{pago.id}/marcar-pagado",
            json={"transaccion_id": str(tx.id)},
            headers=h,
        )
        assert r.status_code == 409
