# backend/tests/test_presupuesto_aprobar_realmongo.py
"""Aprobación del presupuesto — TRANSACCIÓN MULTI-DOC (regla 8/F-09) contra Mongo REAL.

MARCADO PARA AUDITORÍA KIMI (§2.4 aprobar + regla 8 + saga O1).

mongomock NO soporta sesiones/transacciones → estos tests exigen un replica set real
(@requires_real_mongo; CI lo provee, local con COMPAS_TEST_MONGO_URI). Cubren:
  • happy: fija monto_definido (null→sugerido, acotada conserva) + mes→definido.
  • idempotencia: replay de la misma Idempotency-Key devuelve la respuesta original.
  • "aprobación interrumpida CONVERGE" en los DOS puntos de fallo (Kimi):
      (a) abort de la transacción de datos → rollback total (atomicidad).
      (b) fallo del emit de auditoría tras el commit → compensación (saga O1).
    Tras cada fallo, re-ejecutar CONVERGE al estado definido."""

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
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

PWD = "clave-larga-1234"


@pytest.mark.requires_real_mongo
class TestAprobarReal:
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
        dbname = "compas_test_aprobar"
        await client.drop_database(dbname)
        db = client[dbname]
        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
        repository.configure_auth(client, dbname)
        configure_audit(client, dbname)
        for correo, rol in [
            ("fin@roddos.com", Role.financiero),
            ("admin@roddos.com", Role.admin),
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

    async def _token(self, ac, email):
        r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    async def _sembrar(self, estado=EstadoMes.PROPUESTO):
        """Mes + 2 líneas vigentes: una acotada (1.200.000), una sin acotar
        (sugerido 1.000.000 → debe tomar el sugerido al aprobar)."""
        mc = MesControl(
            mes="2026-07-01", saldo_inicial_caja=Decimal("0"), estado=estado
        )
        await mc.insert()
        r1 = Rubro(grupo="operacion", nombre="Arriendos", orden=4, es_sistema=False)
        r2 = Rubro(grupo="operacion", nombre="Servicios", orden=5, es_sistema=False)
        await r1.insert()
        await r2.insert()

        async def _ln(rid, sug, defi):
            ln = PresupuestoLinea(
                mes_id=mc.id,
                rubro_id=rid,
                monto_sugerido=Decimal(sug),
                prom_3m=Decimal(sug),
                tendencia_mes=Decimal("0"),
                crec_pct=Decimal("0"),
                historia_incompleta=False,
                monto_definido=Decimal(defi) if defi else None,
            )
            await ln.insert()
            return ln

        acotada = await _ln(r1.id, "1000000", "1200000")
        sin_acotar = await _ln(r2.id, "1000000", None)
        return mc, acotada, sin_acotar

    async def test_aprobar_happy_atomico(self, entorno):
        ac, db = entorno
        h = await self._token(ac, "admin@roddos.com")
        mc, acotada, sin_acotar = await self._sembrar()
        r = await ac.post(
            "/api/v1/meses/2026-07/presupuesto/aprobar",
            headers={**h, "Idempotency-Key": "ap-1"},
        )
        assert r.status_code == 200
        assert r.json()["estado"] == "definido"
        # acotada conserva; sin acotar toma el sugerido (D2)
        a2 = await PresupuestoLinea.get(acotada.id)
        s2 = await PresupuestoLinea.get(sin_acotar.id)
        assert a2.monto_definido == Decimal("1200000")
        assert s2.monto_definido == Decimal("1000000")
        mc2 = await MesControl.get(mc.id)
        assert mc2.estado is EstadoMes.DEFINIDO
        assert mc2.definido_por is not None and mc2.definido_at is not None
        n = await db["audit_log"].count_documents({"evento": "presupuesto.definido"})
        assert n == 1

    async def test_idempotencia_replay(self, entorno):
        ac, db = entorno
        h = await self._token(ac, "admin@roddos.com")
        await self._sembrar()
        r1 = await ac.post(
            "/api/v1/meses/2026-07/presupuesto/aprobar",
            headers={**h, "Idempotency-Key": "ap-x"},
        )
        r2 = await ac.post(
            "/api/v1/meses/2026-07/presupuesto/aprobar",
            headers={**h, "Idempotency-Key": "ap-x"},
        )
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json() == r2.json()  # replay de la respuesta original
        # el replay NO re-ejecuta: un solo evento de auditoría
        n = await db["audit_log"].count_documents({"evento": "presupuesto.definido"})
        assert n == 1

    async def test_convergencia_abort_datos(self, entorno, monkeypatch):
        # (a) Falla la última escritura de la transacción → abort → rollback TOTAL
        # (las líneas guardadas dentro de la sesión se revierten). Luego CONVERGE.
        ac, db = entorno
        h = await self._token(ac, "admin@roddos.com")
        mc, acotada, sin_acotar = await self._sembrar()

        orig = MesControl.save

        async def flaky(self, *a, **k):
            if k.get("session") is not None:
                raise RuntimeError("caída a mitad de la transacción de datos")
            return await orig(self, *a, **k)

        monkeypatch.setattr(MesControl, "save", flaky)
        with pytest.raises(RuntimeError):
            await ac.post(
                "/api/v1/meses/2026-07/presupuesto/aprobar",
                headers={**h, "Idempotency-Key": "ap-a"},
            )
        # rollback: nada cambió
        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO
        assert (await PresupuestoLinea.get(sin_acotar.id)).monto_definido is None
        # la key fallida se liberó → se puede reintentar
        monkeypatch.undo()
        r = await ac.post(
            "/api/v1/meses/2026-07/presupuesto/aprobar",
            headers={**h, "Idempotency-Key": "ap-a"},
        )
        assert r.status_code == 200
        assert (await MesControl.get(mc.id)).estado is EstadoMes.DEFINIDO
        assert (await PresupuestoLinea.get(sin_acotar.id)).monto_definido == Decimal(
            "1000000"
        )

    async def test_convergencia_falla_emit_compensa(self, entorno, monkeypatch):
        # (b) Commit OK, pero el emit de auditoría falla → compensación (saga O1)
        # revierte mes + los monto_definido que eran null. Luego CONVERGE.
        ac, db = entorno
        h = await self._token(ac, "admin@roddos.com")
        mc, acotada, sin_acotar = await self._sembrar()

        async def boom(*a, **k):
            raise RuntimeError("auditoría caída")

        monkeypatch.setattr("app.presupuesto.service.emit_audit", boom)
        with pytest.raises(RuntimeError):
            await ac.post(
                "/api/v1/meses/2026-07/presupuesto/aprobar",
                headers={**h, "Idempotency-Key": "ap-b"},
            )
        # compensado: mes de vuelta a propuesto; la línea null vuelve a null;
        # la acotada NO se toca (dato legítimo preservado).
        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO
        assert (await PresupuestoLinea.get(sin_acotar.id)).monto_definido is None
        assert (await PresupuestoLinea.get(acotada.id)).monto_definido == Decimal(
            "1200000"
        )
        # ningún evento persistió
        assert (
            await db["audit_log"].count_documents({"evento": "presupuesto.definido"})
            == 0
        )
        # converge al reintentar
        monkeypatch.undo()
        r = await ac.post(
            "/api/v1/meses/2026-07/presupuesto/aprobar",
            headers={**h, "Idempotency-Key": "ap-b"},
        )
        assert r.status_code == 200
        assert (await MesControl.get(mc.id)).estado is EstadoMes.DEFINIDO
