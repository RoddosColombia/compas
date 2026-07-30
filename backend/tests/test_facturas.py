# backend/tests/test_facturas.py
"""IVA C11 (PR-2a) — entidad Factura + CRUD (carga de facturas para liquidar el IVA).

mongomock basta (la unicidad real del índice (tercero_nit, numero) va con
@requires_real_mongo). El IVA se calcula en el backend (regla 1): la carga entrega
base_gravable + tarifa; el servicio deriva iva_valor y total. Baja LÓGICA (anular):
una factura mal cargada no se borra (audit), se marca activo=false.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    configure_audit(c, "compas_test")
    yield c
    reset_audit()


def _compra(**kw):
    base = {
        "tipo": "compra",
        "origen": "auteco",
        "numero": "FC-001",
        "tercero_nombre": "Auteco S.A.S.",
        "tercero_nit": "860024781",
        "fecha": "2026-02-10",
        "base_gravable": Decimal("1000000"),
        "tarifa_iva": Decimal("0.19"),
        "deducible": True,
    }
    base.update(kw)
    return base


async def test_crear_factura_calcula_iva_y_total_y_emite_evento(db):
    from app.facturas import service

    f = await service.crear_factura(usuario_id="u1", **_compra())
    assert f.iva_valor == Decimal("190000.00")  # base × 0.19
    assert f.total == Decimal("1190000.00")  # base + IVA
    assert f.activo is True
    # el evento factura.creada quedó en el audit log
    doc = await db["compas_test"]["audit_log"].find_one({"evento": "factura.creada"})
    assert doc is not None


async def test_crear_factura_venta_calcula_iva(db):
    from app.facturas import service

    f = await service.crear_factura(
        usuario_id="u1",
        tipo="venta",
        origen="moto",
        numero="FV-100",
        tercero_nombre="Cliente X",
        tercero_nit="79999999",
        fecha="2026-03-01",
        base_gravable=Decimal("164900"),
        tarifa_iva=Decimal("0.19"),
        deducible=False,
    )
    assert f.tipo == "venta"
    assert f.iva_valor == Decimal("31331.00")


async def test_crear_factura_duplicada_por_tercero_y_numero_es_409(db):
    from app.facturas import service

    await service.crear_factura(usuario_id="u1", **_compra())
    with pytest.raises(service.FacturasError) as e:
        await service.crear_factura(usuario_id="u1", **_compra())
    assert e.value.status == 409


async def test_mismo_numero_distinto_nit_conviven(db):
    from app.facturas import service

    await service.crear_factura(usuario_id="u1", **_compra(numero="1"))
    # otro proveedor con el mismo número de factura → NO colisiona
    f = await service.crear_factura(
        usuario_id="u1", **_compra(numero="1", tercero_nit="900111222")
    )
    assert f.id is not None


async def test_listar_facturas_filtra_activas(db):
    from app.facturas import service

    f1 = await service.crear_factura(usuario_id="u1", **_compra(numero="A"))
    await service.crear_factura(usuario_id="u1", **_compra(numero="B"))
    await service.anular_factura(factura_id=str(f1.id), usuario_id="u1")

    todas = await service.listar_facturas()
    activas = await service.listar_facturas(activo=True)
    assert len(todas) == 2
    assert len(activas) == 1


async def test_anular_factura_es_baja_logica_y_emite_evento(db):
    from app.facturas import service

    f = await service.crear_factura(usuario_id="u1", **_compra())
    anulada = await service.anular_factura(factura_id=str(f.id), usuario_id="u1")
    assert anulada.activo is False
    doc = await db["compas_test"]["audit_log"].find_one({"evento": "factura.anulada"})
    assert doc is not None
    # anular dos veces → 409
    with pytest.raises(service.FacturasError) as e:
        await service.anular_factura(factura_id=str(f.id), usuario_id="u1")
    assert e.value.status == 409


@pytest.mark.parametrize("compuerta_activa", [True, False])
async def test_proyeccion_iva_segun_compuerta(db, compuerta_activa):
    """CR-E2-COMPUERTA (parametriza el antiguo test_proyeccion_resta_iva...):
    con la compuerta ENCENDIDA una venta con IVA en C1-2026 hace que la proyección
    reste ese IVA en el mes DIAN (13-may-26 → índice 4); APAGADA (default) el IVA NO
    alimenta la proyección y la serie queda en cero, aunque la factura esté cargada."""
    from decimal import Decimal

    from app.domain.configuracion import Configuracion
    from app.domain.modelo_moto import ModeloMoto
    from app.domain.parametros_proyeccion import ParametrosProyeccion
    from app.facturas import service
    from app.proyeccion import service as proy

    await Configuracion(
        clave="IVA_ALIMENTA_PROYECCION",
        valor_json={"activa": compuerta_activa},
        vigente_desde="2026-01-01",
    ).insert()
    await Configuracion(
        clave="CALENDARIO_DIAN",
        valor_json={
            "2026": {
                "ene_abr": "2026-05-13",
                "may_ago": "2026-09-10",
                "sep_dic": "2027-01-14",
            }
        },
        vigente_desde="2026-01-01",
    ).insert()
    await ParametrosProyeccion(
        vigente_desde="2026-01-01",
        caja_inicial=Decimal("0"),
        caja_minima=Decimal("0"),
        motos_base=0,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=8,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=0,
        base_auteco_dias=0,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("0"),
        gps_moto=Decimal("0"),
        costo_moto_nueva=Decimal("0"),
        deuda=Decimal("0"),
        tasa_deuda=Decimal("0"),
        mes_inicio_deuda=0,
        meses_deuda=0,
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
    ).insert()
    await ModeloMoto(
        nombre="Raider",
        costo_auteco=Decimal("0"),
        precio_venta_con_iva=Decimal("0"),
        cuota_inicial=Decimal("0"),
        cuota_semanal=Decimal("0"),
        plazo_semanas=6,
        matricula=Decimal("0"),
        participacion_mix=Decimal("1"),
        orden=0,
    ).insert()
    # venta C1-2026: IVA generado 190000 → neto a pagar 190000
    await service.crear_factura(
        usuario_id="u1",
        tipo="venta",
        origen="moto",
        numero="FV-1",
        tercero_nombre="Cliente",
        tercero_nit="79",
        fecha="2026-02-01",
        base_gravable=Decimal("1000000"),
        tarifa_iva=Decimal("0.19"),
        deducible=False,
    )
    res = await proy.proyectar_vigente(
        escenario="base", mes_inicio=(2026, 1), horizonte_meses=8
    )
    if compuerta_activa:
        # 13-may-26 = índice 4 desde ene-2026; el IVA sale ahí (negativo) y solo ahí
        assert res["meses"][4]["iva"] == "-190000.00"
        assert res["meses"][3]["iva"] == "0.00"
        # fondo de provisión: reserva 47500/mes en ene-abr (190000/4); saldo lleno en
        # abr, el pago de may lo vacía. Serie informativa (no mueve la caja del motor).
        fondo = res["fondo_provision"]
        assert fondo[0] == {
            "mes": "2026-01",
            "reserva": "47500.00",
            "pago": "0.00",
            "saldo": "47500.00",
        }
        assert fondo[3]["saldo"] == "190000.00"
        assert fondo[4] == {
            "mes": "2026-05",
            "reserva": "0.00",
            "pago": "190000.00",
            "saldo": "0.00",
        }
    else:
        # compuerta apagada: la factura NO mueve la proyección (D-12)
        assert all(m["iva"] == "0.00" for m in res["meses"])
        assert res["fondo_provision"] == []


async def test_a14_compuerta_apagada_proyeccion_identica_bit_a_bit(db):
    """A14 / CR-E2-COMPUERTA (criterio central del CEO): con facturas cargadas y la
    compuerta APAGADA, GET /proyeccion es idéntico BIT A BIT al estado sin facturas
    (candado de D-12). Con CONTROL NEGATIVO en el mismo test y el mismo fixture: al
    ENCENDER la compuerta la proyección SÍ cambia (si no cambiara, el escenario no
    ejercita el puente y el candado sería vacuo). Se siembra CALENDARIO_DIAN para que el
    egreso de IVA tenga una fecha real y el escenario sea sensible."""
    from decimal import Decimal

    from app.domain.configuracion import Configuracion
    from app.domain.modelo_moto import ModeloMoto
    from app.domain.parametros_proyeccion import ParametrosProyeccion
    from app.facturas import service
    from app.proyeccion import service as proy

    # calendario real: sin esto el egreso saldría vacío por otra razón (test vacuo)
    await Configuracion(
        clave="CALENDARIO_DIAN",
        valor_json={
            "2026": {
                "ene_abr": "2026-05-13",
                "may_ago": "2026-09-10",
                "sep_dic": "2027-01-14",
            }
        },
        vigente_desde="2026-01-01",
    ).insert()
    await ParametrosProyeccion(
        vigente_desde="2026-01-01",
        caja_inicial=Decimal("0"),
        caja_minima=Decimal("0"),
        motos_base=0,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=8,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=0,
        base_auteco_dias=0,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("0"),
        gps_moto=Decimal("0"),
        costo_moto_nueva=Decimal("0"),
        deuda=Decimal("0"),
        tasa_deuda=Decimal("0"),
        mes_inicio_deuda=0,
        meses_deuda=0,
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
    ).insert()
    await ModeloMoto(
        nombre="Raider",
        costo_auteco=Decimal("0"),
        precio_venta_con_iva=Decimal("0"),
        cuota_inicial=Decimal("0"),
        cuota_semanal=Decimal("0"),
        plazo_semanas=6,
        matricula=Decimal("0"),
        participacion_mix=Decimal("1"),
        orden=0,
    ).insert()

    antes = await proy.proyectar_vigente(
        escenario="base", mes_inicio=(2026, 1), horizonte_meses=8
    )

    # facturas de venta y compra que moverían el IVA con la compuerta encendida
    await service.crear_factura(
        usuario_id="u1",
        tipo="venta",
        origen="moto",
        numero="FV-9",
        tercero_nombre="Cliente",
        tercero_nit="79",
        fecha="2026-02-01",
        base_gravable=Decimal("1000000"),
        tarifa_iva=Decimal("0.19"),
        deducible=False,
    )
    await service.crear_factura(
        usuario_id="u1",
        tipo="compra",
        origen="auteco",
        numero="FC-9",
        tercero_nombre="Auteco",
        tercero_nit="860024781",
        fecha="2026-06-01",
        base_gravable=Decimal("2000000"),
        tarifa_iva=Decimal("0.19"),
        deducible=True,
    )

    # compuerta APAGADA (default, no sembrada) → proyección idéntica bit a bit (D-12)
    despues_off = await proy.proyectar_vigente(
        escenario="base", mes_inicio=(2026, 1), horizonte_meses=8
    )
    assert despues_off == antes

    # CONTROL NEGATIVO: al ENCENDER la compuerta, la MISMA factura SÍ mueve la
    # proyección. Si esto no cambia, el escenario no ejercita el puente → candado vacuo.
    await Configuracion(
        clave="IVA_ALIMENTA_PROYECCION",
        valor_json={"activa": True},
        vigente_desde="2026-01-02",  # vigencia más nueva → gana
    ).insert()
    despues_on = await proy.proyectar_vigente(
        escenario="base", mes_inicio=(2026, 1), horizonte_meses=8
    )
    assert despues_on != antes
    # y concretamente: el IVA generado por la venta sale en el mes DIAN (13-may → idx 4)
    assert despues_on["meses"][4]["iva"] == "-190000.00"


async def test_obtener_facturas_iva_solo_activas_para_liquidar(db):
    """Puente C11: las facturas activas se proyectan a FacturaIva y se liquidan."""
    from app.facturas import service
    from app.iva.liquidacion import liquidar

    # venta C1: IVA generado 190000
    await service.crear_factura(
        usuario_id="u1",
        tipo="venta",
        origen="moto",
        numero="V1",
        tercero_nombre="Cliente",
        tercero_nit="79",
        fecha="2026-02-01",
        base_gravable=Decimal("1000000"),
        tarifa_iva=Decimal("0.19"),
        deducible=False,
    )
    # compra deducible C1: descontable 190000
    await service.crear_factura(usuario_id="u1", **_compra(numero="C1"))
    # compra anulada: NO debe entrar
    fx = await service.crear_factura(usuario_id="u1", **_compra(numero="C2"))
    await service.anular_factura(factura_id=str(fx.id), usuario_id="u1")

    items = await service.obtener_facturas_iva()
    liq = liquidar(items)
    assert len(liq) == 1
    c = liq[0]
    assert c.generado == Decimal("190000")
    assert c.descontable == Decimal("190000")  # solo la activa, no la anulada
    assert c.neto_a_pagar == Decimal("0")
