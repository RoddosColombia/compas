# backend/tests/test_cierre_realmongo.py
"""Cierre de mes — TRANSACCIÓN MULTI-DOC (regla 8) contra Mongo REAL.

MARCADO PARA AUDITORÍA KIMI (los 8 tests exigidos en el certificado R-PLAN 9.4).

mongomock NO soporta transacciones → @requires_real_mongo (CI: replica set). Cubre:
  1. dorado numérico (cuadra a 118 por ambas vías) · 2. exclusión del rubro en la
  disponible · 3. contra-asiento + ancla restaurada al reabrir · 4. doble cierre
  abortado · 5. replay Idempotency-Key sin duplicar · 6-7. convergencia en los 2
  puntos de fallo (abort de datos / fallo de emit) · 8. ajuste omitido si dif==0."""

import os
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.cierre import service
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

PWD = "clave-larga-1234"


@pytest.mark.requires_real_mongo
class TestCierreReal:
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
        dbname = "compas_test_cierre"
        await client.drop_database(dbname)
        db = client[dbname]
        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
        repository.configure_auth(client, dbname)
        configure_audit(client, dbname)
        await repository.create_user(
            User(
                email="admin@roddos.com",
                password_hash=passwords.hash_password(PWD),
                rol=Role.admin,
            )
        )
        await Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=Decimal("50000"),
            vigente_desde="2026-01-01",
        ).insert()
        await Rubro(
            grupo="otros", nombre="Ajuste de conciliación", orden=98, es_sistema=True
        ).insert()
        await Rubro(
            grupo="operacion", nombre="Arriendos", orden=4, es_sistema=False
        ).insert()
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
            "/api/v1/auth/login", json={"email": "admin@roddos.com", "password": PWD}
        )
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    async def _sembrar(self, reportado="118"):
        """M (jun) en ejecución con C_M=120 (100+50−30) y R_M=`reportado`; M+1 (jul)
        abierto con saldo provisional 0."""
        arr = await Rubro.find_one(Rubro.nombre == "Arriendos")
        sb = SaldoBanco(
            banco="bancolombia",
            saldo=Decimal(reportado),
            fecha_reporte="2026-06-30",
        )
        jun = MesControl(
            mes="2026-06-01",
            saldo_inicial_caja=Decimal("100"),
            estado=EstadoMes.EN_EJECUCION,
            saldos_banco=[sb],
        )
        await jun.insert()
        jul = MesControl(
            mes="2026-07-01",
            saldo_inicial_caja=Decimal("0"),
            estado=EstadoMes.SUGERIDO,
        )
        await jul.insert()
        import app.core.ulid as u

        for valor, tipo in [("50", "ingreso"), ("30", "egreso")]:
            await Transaccion(
                fecha="2026-06-10",
                descripcion="mov",
                valor=Decimal(valor),
                tipo_flujo=tipo,
                rubro_id=arr.id,
                mes_id=jun.id,
                banco="bancolombia",
                id_banco=f"MAN-{u.new_ulid()}",
            ).insert()
        return jun, jul, arr

    async def _confirmar(self, ac, h, key="c1"):
        return await ac.post(
            "/api/v1/meses/2026-06/cierre/confirmar",
            headers={**h, "Idempotency-Key": key},
        )

    async def test_dorado_numerico_cuadra_a_118(self, entorno):
        ac, db = entorno
        h = await self._token(ac)
        jun, jul, arr = await self._sembrar("118")
        r = await self._confirmar(ac, h)
        assert r.status_code == 200
        j = r.json()
        assert j["diferencia"] == "-2.00"
        assert j["saldo_inicial_siguiente"] == "118.00"
        # jun cerrado + cierre_info
        jun2 = await MesControl.get(jun.id)
        assert jun2.estado is EstadoMes.CERRADO
        assert jun2.cierre_info.diferencia == Decimal("-2")
        assert jun2.cierre_info.ancla_anterior_siguiente == Decimal("0")
        # ajuste egreso 2 en jul, rubro de sistema
        aj = await Transaccion.get(
            __import__("beanie").PydanticObjectId(j["ajuste_tx_id"])
        )
        assert aj.valor == Decimal("2") and aj.tipo_flujo.value == "egreso"
        assert aj.mes_id == jul.id and aj.fecha == "2026-07-01"
        # M+1 re-anclado a R_M
        jul2 = await MesControl.get(jul.id)
        assert jul2.saldo_inicial_caja == Decimal("118")
        # disponible de jul = 118 (el ajuste se EXCLUYE) → cuadra por ambas vías
        rubro_aj = await service._rubro_ajuste()
        disp = await service._caja_libro(jul.id, rubro_aj.id, jul2.saldo_inicial_caja)
        assert disp == Decimal("118")
        assert await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 1

    async def test_idempotencia_replay(self, entorno):
        ac, db = entorno
        h = await self._token(ac)
        await self._sembrar("118")
        r1 = await self._confirmar(ac, h, "kx")
        r2 = await self._confirmar(ac, h, "kx")
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json() == r2.json()
        assert await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 1

    async def test_doble_cierre_distinta_key_409(self, entorno):
        ac, db = entorno
        h = await self._token(ac)
        await self._sembrar("118")
        assert (await self._confirmar(ac, h, "k1")).status_code == 200
        r2 = await self._confirmar(ac, h, "k2")  # otra key, mes ya cerrado
        assert r2.status_code == 409

    async def test_ajuste_omitido_si_diferencia_cero(self, entorno):
        ac, db = entorno
        h = await self._token(ac)
        jun, jul, arr = await self._sembrar("120")  # R_M = C_M = 120 → dif 0
        r = await self._confirmar(ac, h)
        assert r.status_code == 200
        assert r.json()["ajuste_tx_id"] is None  # B-2: no se crea ajuste
        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("120")
        # no hay transacciones en jul
        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0

    async def test_reabrir_contra_asiento_y_restaura_ancla(self, entorno):
        ac, db = entorno
        h = await self._token(ac)
        jun, jul, arr = await self._sembrar("118")
        await self._confirmar(ac, h)
        aj_id = (await MesControl.get(jun.id)).cierre_info.ajuste_tx_id
        # reabrir a nivel de servicio (evita el step-up MFA del router)
        await service.reabrir_mes(mes="2026-06-01", usuario_id="admin")
        jun2 = await MesControl.get(jun.id)
        assert jun2.estado is EstadoMes.EN_EJECUCION
        assert jun2.cierre_info is None
        # el ajuste original NO se borra (inmutable §2.2.2); hay un contra-asiento
        from beanie import PydanticObjectId

        orig = await Transaccion.get(PydanticObjectId(aj_id))
        assert orig is not None  # sigue existiendo
        contra = await Transaccion.find_one(
            Transaccion.revierte_id == PydanticObjectId(aj_id)
        )
        assert contra is not None
        assert contra.tipo_flujo.value == "ingreso"  # invertido (orig era egreso)
        assert contra.valor == Decimal("2")
        # ancla de jul restaurada al valor previo (0)
        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("0")
        assert await db["audit_log"].count_documents({"evento": "mes.reabierto"}) == 1

    async def test_convergencia_falla_emit_compensa(self, entorno, monkeypatch):
        ac, db = entorno
        h = await self._token(ac)
        jun, jul, arr = await self._sembrar("118")

        async def boom(*a, **k):
            raise RuntimeError("auditoría caída")

        monkeypatch.setattr("app.cierre.service.emit_audit", boom)
        with pytest.raises(RuntimeError):
            await self._confirmar(ac, h, "kf")
        # compensado: jun sigue en ejecución, sin ajuste en jul, ancla restaurada
        assert (await MesControl.get(jun.id)).estado is EstadoMes.EN_EJECUCION
        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("0")
        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
        assert await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 0
        # converge al reintentar
        monkeypatch.undo()
        assert (await self._confirmar(ac, h, "kf2")).status_code == 200
        assert (await MesControl.get(jun.id)).estado is EstadoMes.CERRADO

    async def test_convergencia_abort_datos(self, entorno, monkeypatch):
        ac, db = entorno
        h = await self._token(ac)
        jun, jul, arr = await self._sembrar("118")

        orig = MesControl.save

        async def flaky(self, *a, **k):
            # falla al escribir el estado CERRADO (última escritura) → rollback total
            if k.get("session") is not None and self.estado is EstadoMes.CERRADO:
                raise RuntimeError("caída a mitad de la transacción")
            return await orig(self, *a, **k)

        monkeypatch.setattr(MesControl, "save", flaky)
        with pytest.raises(RuntimeError):
            await self._confirmar(ac, h, "ka")
        monkeypatch.undo()
        # rollback total: jun en ejecución, sin ajuste, jul intacto
        assert (await MesControl.get(jun.id)).estado is EstadoMes.EN_EJECUCION
        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("0")
        # converge
        assert (await self._confirmar(ac, h, "ka2")).status_code == 200
        assert (await MesControl.get(jun.id)).estado is EstadoMes.CERRADO

    async def test_toctou_estado_cambiado_aborta_cierre(self, entorno, monkeypatch):
        # S4-06/B-2 (Kimi I-PR1 cierre): las guardas de estado se evalúan fuera de
        # la transacción — si OTRO proceso cierra el mes ENTRE el check y la
        # transacción, el re-read DENTRO de la sesión debe abortar (409), nunca
        # doble-cerrar (doble ajuste / re-ancla inconsistente).
        ac, db = entorno
        h = await self._token(ac)
        jun, jul, arr = await self._sembrar("118")

        orig = service._conciliar

        async def tramposo(mc, rubro_id):
            r = await orig(mc, rubro_id)
            # "otro proceso" completa un cierre justo después de las guardas
            await db["meses_control"].update_one(
                {"mes": "2026-06-01"}, {"$set": {"estado": "cerrado"}}
            )
            return r

        monkeypatch.setattr(service, "_conciliar", tramposo)
        r = await self._confirmar(ac, h, "toc-1")
        assert r.status_code == 409
        monkeypatch.undo()
        # NO hubo doble cierre: sin ajuste en jul y ancla intacta (el estado
        # 'cerrado' lo puso el proceso concurrente simulado, no este intento).
        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("0")
        assert await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 0

    async def test_toctou_siguiente_cerrado_aborta_cierre(self, entorno, monkeypatch):
        # S4-06/B-2 simétrico: si M+1 queda CERRADO entre el check y la transacción,
        # el cierre aborta (el ajuste se imputaría a un mes inmutable — regla 4).
        ac, db = entorno
        h = await self._token(ac)
        jun, jul, arr = await self._sembrar("118")

        orig = service._conciliar

        async def tramposo(mc, rubro_id):
            r = await orig(mc, rubro_id)
            await db["meses_control"].update_one(
                {"mes": "2026-07-01"}, {"$set": {"estado": "cerrado"}}
            )
            return r

        monkeypatch.setattr(service, "_conciliar", tramposo)
        r = await self._confirmar(ac, h, "toc-2")
        assert r.status_code == 409
        monkeypatch.undo()
        assert (await MesControl.get(jun.id)).estado is EstadoMes.EN_EJECUCION
        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
