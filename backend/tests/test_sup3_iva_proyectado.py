# backend/tests/test_sup3_iva_proyectado.py
"""SUP-3 (CEO 2026-08-22) — el IVA de las ventas FUTURAS entra a la proyección.

Hasta ahora COMPAS solo liquidaba el IVA de facturas REGISTRADAS: las ventas que el
motor proyecta no generaban IVA, así que encender la compuerta no movía un peso y a
partir de sep–dic (con la colocación creciendo) el IVA a pagar se veía en cero. El
modelo v9.1 de Fabián sí lo deriva de las unidades (`IVA!D16:D20`):

    ventas_con_IVA = Σ (unidades_modelo × precio_venta_con_IVA)
    IVA generado   = ventas_con_IVA × 19/119        (`IVA!D17`)
    IVA descontable= compras_Auteco × 19/119         (`IVA!D19`, aquí el costo del
                                                      catálogo YA viene con IVA)
    IVA neto       = generado − descontable          (`IVA!D20`)

Diseño: una función PURA convierte la colocación proyectada en `FacturaIva`
sintéticas y se las pasa al liquidador EXISTENTE junto con las reales — la
liquidación, el calendario DIAN, el saldo a favor y la compuerta no cambian nada.

Candado de precisión (el principio del CEO para el mes en curso): un mes que YA
tiene dato real (mes cerrado o IVA generado registrado) NO se proyecta; su realidad
manda. Nunca se suman las dos cosas.
"""

from datetime import date
from decimal import Decimal

from app.iva.liquidacion import (
    FacturaIva,
    Periodicidad,
    liquidar,
)
from app.iva.proyectado import ModeloIva, facturas_iva_proyectadas

TARIFA = Decimal("0.19")

RAIDER = ModeloIva(
    nombre="Raider",
    precio_venta_con_iva=Decimal("7800000"),
    costo_auteco_con_iva=Decimal("6720557"),
    mix=Decimal("0.70"),
)
APACHE = ModeloIva(
    nombre="Apache 160",
    precio_venta_con_iva=Decimal("9250000"),
    costo_auteco_con_iva=Decimal("8313971"),
    mix=Decimal("0.30"),
)


def test_una_venta_proyectada_genera_su_iva():
    """10 Raider a 7.800.000 con IVA → 78.000.000 facturados → IVA 19/119."""
    fs = facturas_iva_proyectadas(
        colocacion_por_mes=[10],
        meses_ym=[(2026, 9)],
        modelos=[ModeloIva("Raider", Decimal("7800000"), Decimal("0"), Decimal("1"))],
        tarifa=TARIFA,
    )
    ventas = [f for f in fs if f.tipo == "venta"]
    assert len(ventas) == 1
    esperado = (Decimal("78000000") * TARIFA / (1 + TARIFA)).quantize(Decimal("0.01"))
    assert ventas[0].iva_valor == esperado
    assert ventas[0].fecha == "2026-09-01"


def test_la_compra_a_auteco_genera_el_descontable():
    """El costo del catálogo ya viene CON IVA (prod: Raider 6.720.557), así que el
    descontable se EXTRAE con 19/119 — no se multiplica por 19 % (sería doble IVA)."""
    fs = facturas_iva_proyectadas(
        colocacion_por_mes=[10],
        meses_ym=[(2026, 9)],
        modelos=[ModeloIva("Raider", Decimal("0"), Decimal("6720557"), Decimal("1"))],
        tarifa=TARIFA,
    )
    compras = [f for f in fs if f.tipo == "compra"]
    assert len(compras) == 1
    total = Decimal("67205570")
    assert compras[0].iva_valor == (total * TARIFA / (1 + TARIFA)).quantize(
        Decimal("0.01")
    )
    assert compras[0].deducible is True  # el IVA de Auteco SÍ es descontable


def test_reparte_por_el_mix_de_cada_modelo():
    """Fraccionario (como v9.1 en meses proyectados): total × mix × precio."""
    fs = facturas_iva_proyectadas(
        colocacion_por_mes=[100],
        meses_ym=[(2026, 9)],
        modelos=[RAIDER, APACHE],
        tarifa=TARIFA,
    )
    venta = next(f for f in fs if f.tipo == "venta")
    ventas_con_iva = Decimal("100") * Decimal("0.70") * Decimal("7800000") + Decimal(
        "100"
    ) * Decimal("0.30") * Decimal("9250000")
    assert venta.iva_valor == (ventas_con_iva * TARIFA / (1 + TARIFA)).quantize(
        Decimal("0.01")
    )


def test_un_mes_con_dato_real_no_se_proyecta():
    """CANDADO de precisión: si el mes ya tiene su IVA registrado (o está cerrado),
    su realidad manda — no se suma una proyección encima."""
    fs = facturas_iva_proyectadas(
        colocacion_por_mes=[10, 10, 10],
        meses_ym=[(2026, 8), (2026, 9), (2026, 10)],
        modelos=[RAIDER],
        tarifa=TARIFA,
        meses_con_dato_real={"2026-08", "2026-09"},
    )
    assert {f.fecha for f in fs} == {"2026-10-01"}


def test_sin_colocacion_no_hay_iva():
    fs = facturas_iva_proyectadas(
        colocacion_por_mes=[0, 0],
        meses_ym=[(2026, 9), (2026, 10)],
        modelos=[RAIDER],
        tarifa=TARIFA,
    )
    assert fs == []


def test_las_sinteticas_entran_al_liquidador_de_siempre():
    """La liquidación no cambia: recibe las proyectadas junto con las reales y
    resuelve el cuatrimestre, el neto y el arrastre como siempre."""
    reales = [
        FacturaIva("venta", "2026-05-01", Decimal("22007214")),
        FacturaIva("compra", "2026-05-15", Decimal("20000000"), True),
    ]
    proyectadas = facturas_iva_proyectadas(
        colocacion_por_mes=[70],
        meses_ym=[(2026, 8)],
        modelos=[RAIDER],
        tarifa=TARIFA,
    )
    liq = liquidar(reales + proyectadas, Periodicidad.cuatrimestral)
    c2 = next(c for c in liq if (c.anio, c.periodo) == (2026, 2))
    # el generado del período incluye lo real de mayo Y lo proyectado de agosto
    gen_proy = next(f for f in proyectadas if f.tipo == "venta").iva_valor
    assert c2.generado == Decimal("22007214") + gen_proy


def test_el_neto_proyectado_es_positivo_cuando_se_vende_con_margen():
    """Precio de venta > costo ⇒ el IVA generado supera al descontable ⇒ hay IVA por
    pagar en los períodos futuros (justo lo que la proyección no veía)."""
    fs = facturas_iva_proyectadas(
        colocacion_por_mes=[70] * 4,
        meses_ym=[(2026, 9), (2026, 10), (2026, 11), (2026, 12)],
        modelos=[RAIDER, APACHE],
        tarifa=TARIFA,
    )
    liq = liquidar(fs, Periodicidad.cuatrimestral)
    c3 = next(c for c in liq if (c.anio, c.periodo) == (2026, 3))
    assert c3.generado > c3.descontable
    assert c3.neto_a_pagar > 0


def test_la_tarifa_es_un_parametro_no_una_constante():
    fs = facturas_iva_proyectadas(
        colocacion_por_mes=[10],
        meses_ym=[(2026, 9)],
        modelos=[ModeloIva("X", Decimal("1190000"), Decimal("0"), Decimal("1"))],
        tarifa=Decimal("0.05"),
    )
    venta = next(f for f in fs if f.tipo == "venta")
    total = Decimal("11900000")
    assert venta.iva_valor == (total * Decimal("0.05") / Decimal("1.05")).quantize(
        Decimal("0.01")
    )


def test_la_fecha_de_la_sintetica_cae_en_su_mes():
    fs = facturas_iva_proyectadas(
        colocacion_por_mes=[5, 5],
        meses_ym=[(2026, 11), (2027, 1)],
        modelos=[RAIDER],
        tarifa=TARIFA,
    )
    assert {f.fecha for f in fs} == {"2026-11-01", "2027-01-01"}
    # y el período se deriva de esa fecha como con cualquier factura
    assert date.fromisoformat(fs[0].fecha).month == 11
