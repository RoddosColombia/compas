# backend/tests/test_presupuesto_acotar_realmongo.py
"""Acotamiento — TRANSACCIÓN MULTI-DOC (S4-00, higiene Kimi) contra Mongo REAL.

MARCADO PARA AUDITORÍA KIMI (§2.4 acotar + regla 8 + saga O1).

S4-00: `acotar_linea` pasó de dos `save` secuenciales (ventana de inconsistencia
si el proceso moría entre ambos) a transacción multi-doc como aprobar/cerrar.
mongomock NO soporta sesiones → los happy-path viven aquí (@requires_real_mongo,
CI replica set); las GUARDAS (RBAC/estado/404/422, que retornan ANTES de la
transacción) siguen en el archivo mongomock hermano."""

import os
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro
from app.presupuesto import service
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

PWD = "clave-larga-1234"


@pytest.mark.requires_real_mongo
class TestAcotarReal:
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
        dbname = "compas_test_acotar"
        await client.drop_database(dbname)
        db = client[dbname]
        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
        repository.configure_auth(client, dbname)
        configure_audit(client, dbname)
        for correo, rol in [
            ("fin@roddos.com", Role.financiero),
            ("dir@roddos.com", Role.directivo),
        ]:
            await repository.create_user(
                User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
            )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, db
        repository.reset_auth()
        reset_audit()
        await client.drop_database(dbname)
        client.close()
        get_settings.cache_clear()

    async def _token(self, ac, email="fin@roddos.com"):
        r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    async def _sembrar(self, estado=EstadoMes.SUGERIDO, definido=None):
        mc = MesControl(
            mes="2026-07-01", saldo_inicial_caja=Decimal("0"), estado=estado
        )
        await mc.insert()
        rubro = Rubro(grupo="operacion", nombre="Arriendos", orden=4)
        await rubro.insert()
        ln = PresupuestoLinea(
            mes_id=mc.id,
            rubro_id=rubro.id,
            monto_sugerido=Decimal("1000000"),
            prom_3m=Decimal("1000000"),
            tendencia_mes=Decimal("0"),
            crec_pct=Decimal("0"),
            historia_incompleta=False,
            monto_definido=Decimal(definido) if definido is not None else None,
        )
        await ln.insert()
        return mc, rubro, ln

    async def test_acotar_fija_monto_y_transiciona_a_propuesto(self, entorno):
        ac, db = entorno
        h = await self._token(ac, "dir@roddos.com")  # Directivo acota (§2.4)
        mc, rubro, _ = await self._sembrar()
        r = await ac.patch(
            f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
            json={"monto_definido": "1200000", "comentario": "renegociado"},
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["monto_definido"] == "1200000.00"
        # M-1: el mes pasó a 'propuesto' — ATÓMICO con la línea (S4-00)
        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO
        ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
        assert len(ln.ajustes) == 1
        assert ln.ajustes[0].comentario == "renegociado"
        assert ln.ajustes[0].valor_anterior is None
        assert ln.ajustes[0].valor_nuevo == Decimal("1200000")

    async def test_acotar_segunda_vez_conserva_propuesto_y_valor_anterior(
        self, entorno
    ):
        ac, _ = entorno
        h = await self._token(ac)
        mc, rubro, _ = await self._sembrar(
            estado=EstadoMes.PROPUESTO, definido="1200000"
        )
        r = await ac.patch(
            f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
            json={"monto_definido": "1500000"},
            headers=h,
        )
        assert r.status_code == 200
        ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
        assert ln.monto_definido == Decimal("1500000")
        assert ln.ajustes[-1].valor_anterior == Decimal("1200000")
        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO

    async def test_acotar_abort_datos_rollback_total(self, entorno, monkeypatch):
        # S4-00 (el caso que motivó la transacción): si la escritura del MES falla,
        # la LÍNEA tampoco queda — antes quedaba el ajuste sin la transición.
        ac, _ = entorno
        mc, rubro, ln0 = await self._sembrar()

        orig = MesControl.save

        async def flaky(self, *a, **k):
            if k.get("session") is not None:
                raise RuntimeError("caída entre línea y mes")
            return await orig(self, *a, **k)

        monkeypatch.setattr(MesControl, "save", flaky)
        with pytest.raises(RuntimeError):
            await service.acotar_linea(
                mes="2026-07-01",
                rubro_id=str(rubro.id),
                monto_definido=Decimal("1200000"),
                comentario="x",
                usuario_id="u1",
            )
        monkeypatch.undo()
        # rollback TOTAL: ni ajuste ni monto ni estado
        ln = await PresupuestoLinea.get(ln0.id)
        assert ln.monto_definido is None and len(ln.ajustes) == 0
        assert (await MesControl.get(mc.id)).estado is EstadoMes.SUGERIDO

    async def test_acotar_aborta_si_mes_sale_de_acotable_en_la_sesion(
        self, entorno, monkeypatch
    ):
        # A-6 (parte 1, TOCTOU): la guarda de estado corre FUERA de la transacción.
        # Si entre esa guarda y la sesión otro proceso saca el mes de estado acotable
        # (cierre/aprobación), el re-read DENTRO de la sesión aborta con 409 y NADA se
        # escribe. Se simula: la lectura CON session devuelve el mes ya CERRADO.
        _, _ = entorno
        mc, rubro, ln0 = await self._sembrar()
        orig = MesControl.find_one

        async def _find_one(*a, **k):
            doc = await orig(*a, **k)
            if k.get("session") is not None and doc is not None:
                doc.estado = EstadoMes.CERRADO  # cambio concurrente tras la guarda
            return doc

        monkeypatch.setattr(MesControl, "find_one", _find_one)
        with pytest.raises(service.AcotarError) as ei:
            await service.acotar_linea(
                mes="2026-07-01",
                rubro_id=str(rubro.id),
                monto_definido=Decimal("1200000"),
                comentario="x",
                usuario_id="u1",
            )
        assert ei.value.status == 409
        monkeypatch.undo()
        # nada se escribió: la línea y el mes quedan intactos
        ln = await PresupuestoLinea.get(ln0.id)
        assert ln.monto_definido is None and len(ln.ajustes) == 0
        assert (await MesControl.get(mc.id)).estado is EstadoMes.SUGERIDO

    async def test_acotar_concurrente_no_pierde_ajustes(self, entorno):
        # A-6 (parte 2): el $push posicional (no replace de la lista) hace que dos
        # acotares concurrentes sobre la MISMA línea NO se pisen — ambos ajustes
        # quedan. Con read-modify-write de la lista, uno habría clobbereado al otro.
        import asyncio

        ac, _ = entorno
        h = await self._token(ac, "dir@roddos.com")
        mc, rubro, _ = await self._sembrar()
        url = f"/api/v1/meses/2026-07/presupuesto/{rubro.id}"
        r1, r2 = await asyncio.gather(
            ac.patch(url, json={"monto_definido": "1200000"}, headers=h),
            ac.patch(url, json={"monto_definido": "1500000"}, headers=h),
        )
        assert r1.status_code == 200 and r2.status_code == 200
        ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
        assert len(ln.ajustes) == 2  # ninguno pisó al otro
        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO

    async def test_reacotar_en_ejecucion_con_comentario_no_transiciona(self, entorno):
        # FIX-G1: con el presupuesto ya aprobado (en_ejecucion) el CEO corrige un
        # monto_definido. Requiere comentario (justificación), fija el monto, registra
        # el ajuste y NO cambia el estado del mes (sigue en ejecución).
        ac, _ = entorno
        h = await self._token(ac, "dir@roddos.com")
        mc, rubro, _ = await self._sembrar(
            estado=EstadoMes.EN_EJECUCION, definido="1000000"
        )
        r = await ac.patch(
            f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
            json={"monto_definido": "1300000", "comentario": "recorte por caja julio"},
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["monto_definido"] == "1300000.00"
        # NO transiciona: sigue en ejecución (regla FIX-G1)
        assert (await MesControl.get(mc.id)).estado is EstadoMes.EN_EJECUCION
        ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
        assert len(ln.ajustes) == 1
        assert ln.ajustes[-1].comentario == "recorte por caja julio"
        assert ln.ajustes[-1].valor_anterior == Decimal("1000000")
        assert ln.ajustes[-1].valor_nuevo == Decimal("1300000")

    async def test_reacotar_en_ejecucion_concurrente_no_pierde_ajustes(self, entorno):
        # FIX-G1 + A-6: dos re-acotaciones concurrentes en ejecución no se pisan
        # (mismo $push posicional) y el mes NO transiciona.
        import asyncio

        ac, _ = entorno
        h = await self._token(ac, "dir@roddos.com")
        mc, rubro, _ = await self._sembrar(
            estado=EstadoMes.EN_EJECUCION, definido="1000000"
        )
        url = f"/api/v1/meses/2026-07/presupuesto/{rubro.id}"
        r1, r2 = await asyncio.gather(
            ac.patch(
                url, json={"monto_definido": "1200000", "comentario": "a"}, headers=h
            ),
            ac.patch(
                url, json={"monto_definido": "1500000", "comentario": "b"}, headers=h
            ),
        )
        assert r1.status_code == 200 and r2.status_code == 200
        ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
        assert len(ln.ajustes) == 2  # ninguno pisó al otro
        assert (await MesControl.get(mc.id)).estado is EstadoMes.EN_EJECUCION

    async def test_acotar_compensa_si_falla_auditoria(self, entorno, monkeypatch):
        # M-2 (saga O1): commit OK pero el emit falla → compensación transaccional.
        ac, db = entorno
        h = await self._token(ac)
        mc, rubro, ln0 = await self._sembrar()

        async def _boom(*a, **k):
            raise RuntimeError("audit caído")

        monkeypatch.setattr("app.presupuesto.service.emit_audit", _boom)
        with pytest.raises(RuntimeError):
            await service.acotar_linea(
                mes="2026-07-01",
                rubro_id=str(rubro.id),
                monto_definido=Decimal("1200000"),
                comentario="x",
                usuario_id="u1",
            )
        monkeypatch.undo()
        ln = await PresupuestoLinea.get(ln0.id)
        assert ln.monto_definido is None  # revertido
        assert len(ln.ajustes) == 0  # ajuste retirado
        assert (await MesControl.get(mc.id)).estado is EstadoMes.SUGERIDO
        assert (
            await db["audit_log"].count_documents({"evento": "presupuesto.acotado"})
            == 0
        )
        # converge al reintentar
        r = await ac.patch(
            f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
            json={"monto_definido": "1200000"},
            headers=h,
        )
        assert r.status_code == 200
        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO
