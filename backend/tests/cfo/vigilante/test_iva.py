# backend/tests/cfo/vigilante/test_iva.py
"""FABS · vigilante — Task 6: evaluador + `generar_y_entregar_iva` (tesorería IVA,
proactivo).

Dos capas de test, como `test_disparadores.py`/`test_alerta.py`:
(1) los 3 helpers de lectura (`_fondo_mes_actual`/`_proximo_dian`/`_disponible_real`)
se prueban DIRECTO — monkeypatch de sus DEPENDENCIAS (`proy_service.
proyectar_vigente`, `fact_service.obtener_periodicidad`/`obtener_calendario_dian`,
`iva_calc.iva_cuatrimestre`, `conciliacion`) a nivel de módulo, nunca de los helpers
mismos, para que corra su cuerpo real (el query a `MesControl`, las ramas
`CierreError`/`sin_dato`, el catch de `ProyeccionError`, el match de fila del fondo);
(2) `evaluar_iva`/`generar_y_entregar_iva` se prueban con los helpers monkeypateados
(mismo patrón que `evaluar_disparadores` en `test_disparadores.py`, que a su vez
monkeypatchea `_disparador_real`). Auditoría verificada contra mongomock vía
`service.configure_audit` (AuditLog es un BaseModel, no un Document — no se puede
`AuditLog.find_one`)."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.audit import service as audit_service
from app.cfo.vigilante import iva as I
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota, today_bogota
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.iva.liquidacion import Periodicidad, clave_dian
from app.iva.liquidacion import periodo_de as _periodo_de
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.fixture
def audit_col():
    client = AsyncMongoMockClient()
    audit_service.configure_audit(client, "compas_test_audit")
    yield client["compas_test_audit"]["audit_log"]
    audit_service.reset_audit()


def _async(v):
    async def _f():
        return v

    return _f()


class FakeTg:
    def __init__(self):
        self.enviados = []

    async def enviar(self, chat_id, texto):
        self.enviados.append((chat_id, texto))


def _fake_lecturas(
    monkeypatch,
    *,
    reserva_objetivo="10000",
    reserva_mes="2500",
    proximo=None,
    proximo_monto=None,
    disponible=None,
    dias_umbral=30,
):
    async def fake_fondo():
        return (
            Decimal(reserva_objetivo) if reserva_objetivo is not None else None,
            Decimal(reserva_mes) if reserva_mes is not None else None,
        )

    async def fake_proximo():
        return (
            proximo,
            Decimal(proximo_monto) if proximo_monto is not None else None,
        )

    async def fake_disponible():
        return Decimal(disponible) if disponible is not None else None

    async def fake_umbral():
        return dias_umbral

    monkeypatch.setattr(I, "_fondo_mes_actual", fake_fondo)
    monkeypatch.setattr(I, "_proximo_dian", fake_proximo)
    monkeypatch.setattr(I, "_disponible_real", fake_disponible)
    monkeypatch.setattr(I, "leer_alerta_iva_dias", fake_umbral)


# --- helpers de lectura, DIRECTO (sus cuerpos reales, no monkeypateados) -----


@pytest.mark.asyncio
async def test_disponible_real_devuelve_consolidado(db, monkeypatch):
    await MesControl(
        mes="2026-08-01",
        estado=EstadoMes.EN_EJECUCION,
        saldo_inicial_caja=Decimal("0"),
    ).insert()

    async def fake_conciliacion(mes):
        assert mes == "2026-08-01"
        return {"consolidado_reportado": "12345", "sin_dato": []}

    monkeypatch.setattr(I, "conciliacion", fake_conciliacion)
    assert await I._disponible_real() == Decimal("12345")


@pytest.mark.asyncio
async def test_disponible_real_none_sin_mes_en_ejecucion(db):
    assert await I._disponible_real() is None


@pytest.mark.asyncio
async def test_disponible_real_none_si_cierre_error(db, monkeypatch):
    await MesControl(
        mes="2026-08-01",
        estado=EstadoMes.EN_EJECUCION,
        saldo_inicial_caja=Decimal("0"),
    ).insert()

    async def fake_conciliacion(mes):
        raise I.CierreError("solo se concilia un mes en ejecución", 409)

    monkeypatch.setattr(I, "conciliacion", fake_conciliacion)
    assert await I._disponible_real() is None


@pytest.mark.asyncio
async def test_disponible_real_none_si_bancos_sin_dato(db, monkeypatch):
    await MesControl(
        mes="2026-08-01",
        estado=EstadoMes.EN_EJECUCION,
        saldo_inicial_caja=Decimal("0"),
    ).insert()

    async def fake_conciliacion(mes):
        return {"consolidado_reportado": "500", "sin_dato": ["bancolombia"]}

    monkeypatch.setattr(I, "conciliacion", fake_conciliacion)
    assert await I._disponible_real() is None


@pytest.mark.asyncio
async def test_fondo_mes_actual_extrae_saldo_y_reserva(monkeypatch):
    mes_actual = f"{now_bogota().year:04d}-{now_bogota().month:02d}"

    async def fake_proyectar(**kwargs):
        return {
            "fondo_provision": [
                {"mes": mes_actual, "reserva": "2500", "pago": "0", "saldo": "10000"},
                {"mes": "2099-01", "reserva": "999", "pago": "0", "saldo": "999"},
            ]
        }

    monkeypatch.setattr(I.proy_service, "proyectar_vigente", fake_proyectar)
    reserva_objetivo, reserva_mes = await I._fondo_mes_actual()
    assert reserva_objetivo == Decimal("10000")
    assert reserva_mes == Decimal("2500")


@pytest.mark.asyncio
async def test_fondo_mes_actual_none_si_proyeccion_error(monkeypatch):
    async def fake_proyectar(**kwargs):
        raise I.ProyeccionError("sin modelos activos", 409)

    monkeypatch.setattr(I.proy_service, "proyectar_vigente", fake_proyectar)
    assert await I._fondo_mes_actual() == (None, None)


@pytest.mark.asyncio
async def test_fondo_mes_actual_none_si_sin_fila_del_mes(monkeypatch):
    async def fake_proyectar(**kwargs):
        return {
            "fondo_provision": [
                {"mes": "2099-01", "reserva": "1", "pago": "0", "saldo": "1"}
            ]
        }

    monkeypatch.setattr(I.proy_service, "proyectar_vigente", fake_proyectar)
    assert await I._fondo_mes_actual() == (None, None)


@pytest.mark.asyncio
async def test_proximo_dian_compone_periodicidad_y_calendario(monkeypatch):
    hoy = today_bogota()
    anio, idx = _periodo_de(hoy.isoformat(), Periodicidad.cuatrimestral)
    clave = clave_dian(idx, Periodicidad.cuatrimestral)
    fecha_dian = "2099-12-31"  # lejos: dias siempre positivo, test estable en el tiempo

    async def fake_periodicidad():
        return Periodicidad.cuatrimestral

    async def fake_calendario():
        return {str(anio): {clave: fecha_dian}}

    class _FakeIvaRes:
        disponible = True
        valor = Decimal("777000")

    async def fake_iva_cuatrimestre():
        return _FakeIvaRes()

    monkeypatch.setattr(I.fact_service, "obtener_periodicidad", fake_periodicidad)
    monkeypatch.setattr(I.fact_service, "obtener_calendario_dian", fake_calendario)
    monkeypatch.setattr(I.iva_calc, "iva_cuatrimestre", fake_iva_cuatrimestre)

    proximo, proximo_monto = await I._proximo_dian()
    assert proximo is not None
    assert proximo["fecha"] == fecha_dian
    assert proximo_monto == Decimal("777000")


@pytest.mark.asyncio
async def test_proximo_dian_none_sin_fecha_en_calendario(monkeypatch):
    async def fake_periodicidad():
        return Periodicidad.cuatrimestral

    async def fake_calendario():
        return {}  # sin vigencia: proximo_pago no inventa una fecha (R5)

    class _FakeIvaRes:
        disponible = False
        valor = None

    async def fake_iva_cuatrimestre():
        return _FakeIvaRes()

    monkeypatch.setattr(I.fact_service, "obtener_periodicidad", fake_periodicidad)
    monkeypatch.setattr(I.fact_service, "obtener_calendario_dian", fake_calendario)
    monkeypatch.setattr(I.iva_calc, "iva_cuatrimestre", fake_iva_cuatrimestre)

    proximo, proximo_monto = await I._proximo_dian()
    assert proximo is None
    assert proximo_monto is None


@pytest.mark.asyncio
async def test_proximo_dian_monto_none_si_iva_cuatrimestre_abstiene(monkeypatch):
    """Periodicidad ≠ cuatrimestral: `proximo_pago` sigue funcionando (es
    periodicidad-agnóstico), pero `iva_cuatrimestre()` falla-cerrado a
    `disponible=False` (esa calc asume cuatrimestral) — `proximo_monto` sale None."""
    hoy = today_bogota()
    anio, idx = _periodo_de(hoy.isoformat(), Periodicidad.bimestral)
    clave = clave_dian(idx, Periodicidad.bimestral)
    fecha_dian = "2099-12-31"

    async def fake_periodicidad():
        return Periodicidad.bimestral

    async def fake_calendario():
        return {str(anio): {clave: fecha_dian}}

    class _FakeIvaRes:
        disponible = False
        valor = None

    async def fake_iva_cuatrimestre():
        return _FakeIvaRes()

    monkeypatch.setattr(I.fact_service, "obtener_periodicidad", fake_periodicidad)
    monkeypatch.setattr(I.fact_service, "obtener_calendario_dian", fake_calendario)
    monkeypatch.setattr(I.iva_calc, "iva_cuatrimestre", fake_iva_cuatrimestre)

    proximo, proximo_monto = await I._proximo_dian()
    assert proximo is not None and proximo["fecha"] == fecha_dian
    assert proximo_monto is None


# --- evaluar_iva -------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispara_por_dias_cerca_dian(monkeypatch):
    _fake_lecturas(
        monkeypatch,
        proximo={"fecha": "2026-09-10", "dias": 10},
        proximo_monto="500000",
        dias_umbral=30,
        disponible="999999999",  # sobra: no debe disparar también por descubierto
    )
    res = await I.evaluar_iva()
    assert res is not None
    assert [d.tipo for d in res.disparos] == ["dian_cerca"]
    monto = next(r for r in res.resultados if r.concepto == "ivates_proximo_pago")
    assert monto.valor == Decimal("500000") and monto.disponible


@pytest.mark.asyncio
async def test_dispara_por_descubierto(monkeypatch):
    _fake_lecturas(
        monkeypatch,
        reserva_objetivo="10000",
        disponible="1000",  # bajo la reserva
        proximo={"fecha": "2026-12-31", "dias": 200},  # lejos: no dispara por DIAN
        proximo_monto="500000",
        dias_umbral=30,
    )
    res = await I.evaluar_iva()
    assert res is not None
    assert [d.tipo for d in res.disparos] == ["descubierto"]
    faltante = next(r for r in res.resultados if r.concepto == "ivates_faltante")
    assert faltante.valor == Decimal("9000")


@pytest.mark.asyncio
async def test_dispara_por_ambos(monkeypatch):
    _fake_lecturas(
        monkeypatch,
        reserva_objetivo="10000",
        disponible="1000",
        proximo={"fecha": "2026-09-10", "dias": 5},
        proximo_monto="500000",
        dias_umbral=30,
    )
    res = await I.evaluar_iva()
    assert res is not None
    assert {d.tipo for d in res.disparos} == {"dian_cerca", "descubierto"}


@pytest.mark.asyncio
async def test_no_dispara_cubierto_y_lejos(monkeypatch):
    _fake_lecturas(
        monkeypatch,
        reserva_objetivo="10000",
        disponible="999999",
        proximo={"fecha": "2026-12-31", "dias": 200},
        proximo_monto="500000",
        dias_umbral=30,
    )
    assert await I.evaluar_iva() is None


@pytest.mark.asyncio
async def test_abstiene_sin_config_de_fondo(monkeypatch):
    """Sin fondo (`ProyeccionError` → `reserva_objetivo=None`): NINGÚN disparo puede
    armar su línea (ambas citan `[[ivates_reserva_objetivo]]`) — abstención total,
    aunque los datos crudos de cada disparador individualmente calificarían (§8: "el
    advisory y el proactivo se abstienen")."""
    _fake_lecturas(
        monkeypatch,
        reserva_objetivo=None,
        reserva_mes=None,
        disponible="1",  # "descubierto" por cifra, pero sin objetivo no hay línea
        proximo={"fecha": "2026-09-10", "dias": 5},  # "cerca", pero sin objetivo
        proximo_monto="500000",
        dias_umbral=30,
    )
    assert await I.evaluar_iva() is None


@pytest.mark.asyncio
async def test_abstiene_sin_fecha_dian_en_calendario(monkeypatch):
    """`proximo_pago` → `None` (R5: sin fecha en `CALENDARIO_DIAN` no se inventa) y
    disponible cubre la reserva: sin ningún disparo."""
    _fake_lecturas(
        monkeypatch,
        reserva_objetivo="10000",
        disponible="999999",
        proximo=None,
        proximo_monto=None,
        dias_umbral=30,
    )
    assert await I.evaluar_iva() is None


@pytest.mark.asyncio
async def test_abstiene_si_periodicidad_no_cuatrimestral_deja_sin_monto(monkeypatch):
    """`iva.iva_cuatrimestre()` falla-cerrado (periodicidad ≠ cuatrimestral) ⇒
    `proximo_monto=None`; aunque `dias` esté cerca, el disparador 'cerca DIAN' no
    puede citar `[[ivates_proximo_pago]]` sin evidencia y se abstiene."""
    _fake_lecturas(
        monkeypatch,
        reserva_objetivo="10000",
        disponible="999999",
        proximo={"fecha": "2026-09-10", "dias": 5},
        proximo_monto=None,
        dias_umbral=30,
    )
    assert await I.evaluar_iva() is None


# --- generar_y_entregar_iva ---------------------------------------------------


def _res_dian_cerca():
    return I.ResultadoIva(
        disparos=[I.Disparo("dian_cerca")],
        resultados=I.armar_conceptos(
            reserva_objetivo=Decimal("10000"),
            reserva_mes=Decimal("2500"),
            proximo_monto=Decimal("500000"),
            proximo_fecha="2026-09-10",
            disponible=None,
        ),
    )


@pytest.mark.asyncio
async def test_dispara_guarda_borrador_audita_y_envia(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    monkeypatch.setattr(I, "evaluar_iva", lambda: _async(_res_dian_cerca()))
    tg = FakeTg()
    monkeypatch.setattr(I, "crear_cliente_telegram", lambda: tg)

    aviso = await I.generar_y_entregar_iva()
    assert aviso is not None
    assert aviso.tipo == "iva_tesoreria" and aviso.estado == "borrador"
    hoy_mes = f"{now_bogota().year:04d}-{now_bogota().month:02d}"
    assert aviso.periodo == hoy_mes
    assert "publicar iva" in tg.enviados[-1][1]
    assert "$500.000" in aviso.texto
    assert "[[" not in aviso.texto
    doc = await audit_col.find_one({"evento": "vigilante.iva.generado"})
    assert doc is not None
    assert doc["metadata"]["disparadores"] == ["dian_cerca"]


@pytest.mark.asyncio
async def test_no_dispara_retira_borrador_pendiente(db, audit_col, monkeypatch):
    # había un borrador de un mes anterior
    await AvisoVigilante(
        tipo="iva_tesoreria",
        periodo="2026-07",
        texto="viejo",
        texto_crudo="c",
        estado="borrador",
        generado_at=now_bogota(),
    ).insert()
    monkeypatch.setattr(I, "evaluar_iva", lambda: _async(None))
    out = await I.generar_y_entregar_iva()
    assert out is None
    viejo = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-07")
    assert viejo.estado == "superado"


@pytest.mark.asyncio
async def test_sin_revisor_configurado_guarda_pero_no_envia(db, audit_col, monkeypatch):
    monkeypatch.delenv("VIGILANTE_REVISOR_TELEGRAM_ID", raising=False)
    monkeypatch.setattr(I, "evaluar_iva", lambda: _async(_res_dian_cerca()))

    aviso = await I.generar_y_entregar_iva()
    assert aviso is not None and aviso.estado == "borrador"
