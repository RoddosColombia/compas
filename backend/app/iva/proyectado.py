# backend/app/iva/proyectado.py
"""SUP-3 (CEO 2026-08-22) — el IVA de las ventas FUTURAS entra a la proyección.

COMPAS solo liquidaba el IVA de facturas REGISTRADAS: las ventas que el motor
proyecta no generaban IVA, así que la compuerta IVA→caja no movía un peso y de
sep–dic en adelante el IVA a pagar se veía en cero. El modelo v9.1 de Fabián sí lo
deriva de las unidades colocadas (hoja `IVA`, filas 16-20):

    ventas_con_IVA  = Σ (unidades_modelo × precio_venta_con_IVA)     (D16)
    IVA generado    = ventas_con_IVA × tarifa/(1+tarifa)             (D17)
    IVA descontable = compras_Auteco × tarifa/(1+tarifa)             (D19)
    IVA neto        = generado − descontable                         (D20)

**Cómo se integra sin tocar nada**: esta capa NO liquida. Convierte la colocación
proyectada en `FacturaIva` sintéticas y se las entrega al liquidador EXISTENTE junto
con las reales — el cuatrimestre, el calendario DIAN, el saldo a favor declarado, el
arrastre y la compuerta siguen exactamente igual.

**Candado de precisión** (el principio del CEO para el mes en curso): un mes que ya
tiene dato real —cerrado, o con su IVA generado registrado— NO se proyecta. Su
realidad manda y jamás se suman las dos cosas.

⚠ El `costo_auteco` del catálogo viene CON IVA (prod: Raider 6.720.557 = 5.638.974 ×
1,19), por eso el descontable se EXTRAE con tarifa/(1+tarifa) en vez de multiplicar
por la tarifa: multiplicar cobraría el IVA dos veces.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.iva.liquidacion import FacturaIva, iva_desde_total


@dataclass(frozen=True)
class ModeloIva:
    """Lo que un modelo del catálogo aporta al IVA: cuánto factura al cliente y
    cuánto cuesta comprarlo (ambos CON IVA), y su peso en la colocación."""

    nombre: str
    precio_venta_con_iva: Decimal
    costo_auteco_con_iva: Decimal
    mix: Decimal


def facturas_iva_proyectadas(
    colocacion_por_mes: list[int],
    meses_ym: list[tuple[int, int]],
    modelos: list[ModeloIva],
    tarifa: Decimal,
    meses_con_dato_real: frozenset[str] | set[str] | None = None,
) -> list[FacturaIva]:
    """Colocación proyectada → `FacturaIva` sintéticas (una venta y una compra por
    mes) listas para el liquidador. Los meses con dato real se omiten enteros.

    El reparto entre modelos es FRACCIONARIO (`total × mix`), como v9.1 en los meses
    proyectados: en el futuro no hay unidades enteras que respetar, y el redondeo
    entero introduciría un sesgo mes a mes."""
    reales = meses_con_dato_real or frozenset()
    fuera: list[FacturaIva] = []
    for i, (anio, mes) in enumerate(meses_ym):
        clave = f"{anio:04d}-{mes:02d}"
        if clave in reales:
            continue  # su realidad manda; no se proyecta encima
        unidades = colocacion_por_mes[i] if i < len(colocacion_por_mes) else 0
        if unidades <= 0:
            continue
        fecha = f"{clave}-01"
        ventas_con_iva = sum(
            (Decimal(unidades) * m.mix * m.precio_venta_con_iva for m in modelos),
            Decimal("0"),
        )
        compras_con_iva = sum(
            (Decimal(unidades) * m.mix * m.costo_auteco_con_iva for m in modelos),
            Decimal("0"),
        )
        generado = iva_desde_total(ventas_con_iva, tarifa)
        descontable = iva_desde_total(compras_con_iva, tarifa)
        if generado > 0:
            fuera.append(FacturaIva("venta", fecha, generado))
        if descontable > 0:
            # el IVA de las compras a Auteco SÍ es descontable (decisión CEO
            # 2026-07-31, ya aplicada a las facturas reales)
            fuera.append(FacturaIva("compra", fecha, descontable, True))
    return fuera
