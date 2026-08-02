# backend/tests/test_caja_saldos_realmongo.py
"""C4 — reporte diario de saldos por banco contra Mongo REAL.

MARCADO PARA AUDITORÍA KIMI (CR-S6 + B-1 atomicidad posicional + D4 + saga O1).

B-1 (Kimi): el upsert usa update atómico posicional por banco (no read-modify-write
de la lista entera) → dos PATCH concurrentes sobre bancos distintos NO se pisan.
mongomock no implementa el operador posicional `$` con fidelidad, así que el
happy-path, la conciliación en la respuesta (D4), la auditoría por banco y la
concurrencia viven aquí (@requires_real_mongo, replica set en CI)."""

import asyncio
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
from app.domain.bancos import Banco
from app.domain.configuracion import Configuracion
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
from app.domain.rubro import Rubro
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

PWD = "clave-larga-1234"


@pytest.mark.requires_real_mongo
class TestReportarSaldosReal:
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
        dbname = "compas_test_caja"
        await client.drop_database(dbname)
        db = client[dbname]
        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
        repository.configure_auth(client, dbname)
        configure_audit(client, dbname)
        for correo, rol in [
            ("fin@roddos.com", Role.financiero),
            ("admin@roddos.com", Role.admin),
            ("consulta@roddos.com", Role.consulta),
        ]:
            await repository.create_user(
                User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
            )
        # Insumos de la conciliación (D4): umbral + rubro de sistema 'Ajuste'.
        await Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=Decimal("50000"),
            vigente_desde="2026-01-01",
        ).insert()
        await Rubro(
            grupo="otros", nombre="Ajuste de conciliación", orden=99, es_sistema=True
        ).insert()
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

    async def _mes(self, saldos=None):
        mc = MesControl(
            mes="2026-07-01",
            saldo_inicial_caja=Decimal("0"),
            estado=EstadoMes.EN_EJECUCION,
            saldos_banco=saldos or [],
        )
        await mc.insert()
        return mc

    def _body(self, banco="global66", saldo="1000000.00", fecha="2026-07-15"):
        return {"saldos": [{"banco": banco, "saldo": saldo, "fecha_reporte": fecha}]}

    # ── Upsert ──

    async def test_agrega_banco_nuevo(self, entorno):
        ac, _ = entorno
        h = await self._token(ac)
        mc = await self._mes()
        r = await ac.patch("/api/v1/meses/2026-07/saldos", json=self._body(), headers=h)
        assert r.status_code == 200
        mc = await MesControl.get(mc.id)
        assert len(mc.saldos_banco) == 1
        sb = mc.saldos_banco[0]
        assert sb.banco is Banco.GLOBAL66
        assert sb.saldo == Decimal("1000000.00")
        assert sb.fecha_reporte == "2026-07-15"

    async def test_reemplaza_saldo_y_fecha_del_banco(self, entorno):
        ac, _ = entorno
        h = await self._token(ac)
        mc = await self._mes(
            saldos=[
                SaldoBanco(
                    banco=Banco.GLOBAL66, saldo=Decimal("5"), fecha_reporte="2026-07-10"
                )
            ]
        )
        r = await ac.patch(
            "/api/v1/meses/2026-07/saldos",
            json=self._body(saldo="7777.00", fecha="2026-07-16"),
            headers=h,
        )
        assert r.status_code == 200
        mc = await MesControl.get(mc.id)
        assert len(mc.saldos_banco) == 1
        assert mc.saldos_banco[0].saldo == Decimal("7777.00")
        assert mc.saldos_banco[0].fecha_reporte == "2026-07-16"

    async def test_correccion_mismo_dia_ok(self, entorno):
        # Misma fecha, nuevo saldo (typo en el reporte de la mañana) — permitido.
        ac, _ = entorno
        h = await self._token(ac)
        mc = await self._mes(
            saldos=[
                SaldoBanco(
                    banco=Banco.GLOBAL66, saldo=Decimal("5"), fecha_reporte="2026-07-15"
                )
            ]
        )
        r = await ac.patch(
            "/api/v1/meses/2026-07/saldos",
            json=self._body(saldo="9.00", fecha="2026-07-15"),
            headers=h,
        )
        assert r.status_code == 200
        mc = await MesControl.get(mc.id)
        assert mc.saldos_banco[0].saldo == Decimal("9.00")

    async def test_no_toca_los_otros_bancos(self, entorno):
        ac, _ = entorno
        h = await self._token(ac)
        mc = await self._mes(
            saldos=[
                SaldoBanco(
                    banco=Banco.BBVA, saldo=Decimal("100"), fecha_reporte="2026-07-10"
                )
            ]
        )
        r = await ac.patch("/api/v1/meses/2026-07/saldos", json=self._body(), headers=h)
        assert r.status_code == 200
        mc = await MesControl.get(mc.id)
        por = {sb.banco: sb for sb in mc.saldos_banco}
        assert por[Banco.BBVA].saldo == Decimal("100")  # intacto
        assert por[Banco.GLOBAL66].saldo == Decimal("1000000.00")

    async def test_dia1_ok(self, entorno):
        ac, _ = entorno
        h = await self._token(ac)
        await self._mes()
        r = await ac.patch(
            "/api/v1/meses/2026-07/saldos",
            json=self._body(fecha="2026-07-01"),
            headers=h,
        )
        assert r.status_code == 200

    # ── D4 — conciliación en la respuesta (idéntica al GET) ──

    async def test_respuesta_trae_conciliacion(self, entorno):
        ac, _ = entorno
        h = await self._token(ac)
        await self._mes()
        r = await ac.patch("/api/v1/meses/2026-07/saldos", json=self._body(), headers=h)
        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["mes"] == "2026-07"
        assert "conciliacion" in cuerpo
        conc = cuerpo["conciliacion"]
        # misma forma que el GET operativo (misma función = misma verdad)
        for k in (
            "por_banco",
            "sin_dato",
            "consolidado_reportado",
            "caja_libro",
            "diferencia",
            "umbral",
            "dentro_de_umbral",
        ):
            assert k in conc, k
        # sin movimientos: reportado = consolidado; caja_libro = saldo_inicial (0)
        assert conc["consolidado_reportado"] == "1000000.00"
        # y coincide con el GET operativo
        g = await ac.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
        assert g.status_code == 200
        assert g.json()["consolidado_reportado"] == conc["consolidado_reportado"]

    # ── Auditoría por banco (D5) ──

    async def test_un_evento_por_banco_con_metadata(self, entorno):
        ac, db = entorno
        h = await self._token(ac)
        await self._mes(
            saldos=[
                SaldoBanco(
                    banco=Banco.GLOBAL66, saldo=Decimal("5"), fecha_reporte="2026-07-10"
                )
            ]
        )
        r = await ac.patch(
            "/api/v1/meses/2026-07/saldos",
            json={
                "saldos": [
                    {
                        "banco": "global66",
                        "saldo": "10.00",
                        "fecha_reporte": "2026-07-16",
                    },
                    {"banco": "bbva", "saldo": "20.00", "fecha_reporte": "2026-07-16"},
                ]
            },
            headers=h,
        )
        assert r.status_code == 200
        eventos = (
            await db["audit_log"]
            .find({"evento": "saldo_banco.reportado"})
            .to_list(length=None)
        )
        assert len(eventos) == 2  # uno por banco tocado
        por_banco = {e["metadata"]["banco"]: e["metadata"] for e in eventos}
        # global66: anterior → nuevo, con valores Y fechas (exigencia Kimi D1)
        g = por_banco["global66"]
        assert g["saldo_anterior"] == "5.00"
        assert g["saldo_nuevo"] == "10.00"
        assert g["fecha_reporte_anterior"] == "2026-07-10"
        assert g["fecha_reporte_nueva"] == "2026-07-16"
        # bbva: banco nuevo → anterior null
        b = por_banco["bbva"]
        assert b["saldo_anterior"] is None
        assert b["fecha_reporte_anterior"] is None
        assert b["saldo_nuevo"] == "20.00"

    # ── O1 — saga fail-closed ──

    async def test_o1_emit_falla_restaura(self, entorno, monkeypatch):
        # commit del saldo OK pero el emit de auditoría cae → se restaura el estado
        # previo del banco (por-banco, B-1) y propaga.
        ac, db = entorno
        h = await self._token(ac)
        mc = await self._mes(
            saldos=[
                SaldoBanco(
                    banco=Banco.GLOBAL66, saldo=Decimal("5"), fecha_reporte="2026-07-10"
                )
            ]
        )

        async def _boom(*a, **k):
            raise RuntimeError("audit caído")

        monkeypatch.setattr("app.caja.service.emit_audit", _boom)
        with pytest.raises(RuntimeError):
            await ac.patch("/api/v1/meses/2026-07/saldos", json=self._body(), headers=h)
        monkeypatch.undo()
        mc = await MesControl.get(mc.id)
        # restaurado: saldo y fecha previos, un solo banco
        assert len(mc.saldos_banco) == 1
        assert mc.saldos_banco[0].saldo == Decimal("5")
        assert mc.saldos_banco[0].fecha_reporte == "2026-07-10"
        assert (
            await db["audit_log"].count_documents({"evento": "saldo_banco.reportado"})
            == 0
        )

    async def test_o1_banco_nuevo_se_retira_al_fallar(self, entorno, monkeypatch):
        # Si el banco era nuevo (no existía) y el emit cae → se hace $pull (no queda).
        ac, _ = entorno
        h = await self._token(ac)
        mc = await self._mes()

        async def _boom(*a, **k):
            raise RuntimeError("audit caído")

        monkeypatch.setattr("app.caja.service.emit_audit", _boom)
        with pytest.raises(RuntimeError):
            await ac.patch("/api/v1/meses/2026-07/saldos", json=self._body(), headers=h)
        monkeypatch.undo()
        mc = await MesControl.get(mc.id)
        assert mc.saldos_banco == []  # el banco nuevo se retiró

    # ── B-1 — concurrencia (dos PATCH sobre bancos distintos) ──

    async def test_concurrencia_bancos_distintos_no_se_pisan(self, entorno):
        ac, _ = entorno
        h = await self._token(ac)
        mc = await self._mes()
        b_g = {
            "saldos": [
                {"banco": "global66", "saldo": "111.00", "fecha_reporte": "2026-07-15"}
            ]
        }
        b_b = {
            "saldos": [
                {"banco": "bbva", "saldo": "222.00", "fecha_reporte": "2026-07-15"}
            ]
        }
        r1, r2 = await asyncio.gather(
            ac.patch("/api/v1/meses/2026-07/saldos", json=b_g, headers=h),
            ac.patch("/api/v1/meses/2026-07/saldos", json=b_b, headers=h),
        )
        assert r1.status_code == 200 and r2.status_code == 200
        mc = await MesControl.get(mc.id)
        por = {sb.banco: sb.saldo for sb in mc.saldos_banco}
        # B-1: ninguno pisó al otro (read-modify-write habría perdido uno)
        assert por.get(Banco.GLOBAL66) == Decimal("111.00")
        assert por.get(Banco.BBVA) == Decimal("222.00")

    # ── A-6 — no-retroceso y estado ATÓMICOS (TOCTOU) ──

    async def test_upsert_no_retroceso_atomico_directo(self, entorno):
        # El no-retroceso vive TAMBIÉN dentro del update atómico, no solo en la
        # validación de snapshot de arriba. Llamando _upsert_saldo directo (como una
        # carrera que ya superó el snapshot con una fecha anterior) el $elemMatch
        # {fecha <= nueva} no casa → releer → 422; el banco NO se mueve.
        from app.caja import service as caja_service

        _, _ = entorno
        mc = await self._mes(
            saldos=[
                SaldoBanco(
                    banco=Banco.GLOBAL66, saldo=Decimal("5"), fecha_reporte="2026-07-20"
                )
            ]
        )
        col = MesControl.get_pymongo_collection()
        with pytest.raises(caja_service.CajaError) as ei:
            await caja_service._upsert_saldo(
                col,
                "2026-07-01",
                caja_service.ReporteBanco(
                    banco=Banco.GLOBAL66,
                    saldo=Decimal("9"),
                    fecha_reporte="2026-07-10",  # retroceso vs 07-20
                ),
            )
        assert ei.value.status == 422
        mc = await MesControl.get(mc.id)
        assert mc.saldos_banco[0].fecha_reporte == "2026-07-20"  # intacto
        assert mc.saldos_banco[0].saldo == Decimal("5")

    async def test_upsert_estado_no_en_ejecucion_atomico_no_escribe(self, entorno):
        # El update atómico exige estado=en_ejecucion. Si el mes se cerró tras el
        # snapshot, la escritura no cuela → 409 y NADA se escribe (ni $set ni $push).
        from app.caja import service as caja_service

        _, _ = entorno
        mc = await self._mes()
        mc.estado = EstadoMes.CERRADO  # cierre concurrente tras el snapshot
        await mc.save()
        col = MesControl.get_pymongo_collection()
        with pytest.raises(caja_service.CajaError) as ei:
            await caja_service._upsert_saldo(
                col,
                "2026-07-01",
                caja_service.ReporteBanco(
                    banco=Banco.GLOBAL66,
                    saldo=Decimal("9"),
                    fecha_reporte="2026-07-15",
                ),
            )
        assert ei.value.status == 409
        mc = await MesControl.get(mc.id)
        assert mc.saldos_banco == []  # no se creó el banco en un mes cerrado

    async def test_upsert_correccion_mismo_dia_pasa_el_elemmatch(self, entorno):
        # Frontera del $lte: misma fecha (corrección del día) SÍ casa el $elemMatch
        # {fecha <= nueva} → actualiza saldo sin tocar la fecha. No es retroceso.
        from app.caja import service as caja_service

        _, _ = entorno
        mc = await self._mes(
            saldos=[
                SaldoBanco(
                    banco=Banco.GLOBAL66, saldo=Decimal("5"), fecha_reporte="2026-07-15"
                )
            ]
        )
        col = MesControl.get_pymongo_collection()
        await caja_service._upsert_saldo(
            col,
            "2026-07-01",
            caja_service.ReporteBanco(
                banco=Banco.GLOBAL66, saldo=Decimal("42"), fecha_reporte="2026-07-15"
            ),
        )
        mc = await MesControl.get(mc.id)
        assert mc.saldos_banco[0].saldo == Decimal("42")
        assert mc.saldos_banco[0].fecha_reporte == "2026-07-15"

    # ── D6 — reintento con el mismo body ──

    async def test_reintento_mismo_body_converge(self, entorno):
        ac, db = entorno
        h = await self._token(ac)
        await self._mes()
        for _ in range(2):
            r = await ac.patch(
                "/api/v1/meses/2026-07/saldos", json=self._body(), headers=h
            )
            assert r.status_code == 200
        mc = await MesControl.find_one(MesControl.mes == "2026-07-01")
        assert len(mc.saldos_banco) == 1
        assert mc.saldos_banco[0].saldo == Decimal("1000000.00")
        # el segundo reporte registra anterior == nuevo (rastro veraz, D6)
        eventos = (
            await db["audit_log"]
            .find({"evento": "saldo_banco.reportado"})
            .sort("timestamp", 1)
            .to_list(length=None)
        )
        assert len(eventos) == 2
        assert eventos[1]["metadata"]["saldo_anterior"] == "1000000.00"
        assert eventos[1]["metadata"]["saldo_nuevo"] == "1000000.00"

    # ── RBAC en real (admin OK) ──

    async def test_admin_ok(self, entorno):
        ac, _ = entorno
        h = await self._token(ac, "admin@roddos.com")
        await self._mes()
        r = await ac.patch("/api/v1/meses/2026-07/saldos", json=self._body(), headers=h)
        assert r.status_code == 200
