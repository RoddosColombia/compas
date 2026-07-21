# backend/tests/test_domain_rubro.py
"""Rubro (Spec §1.2) + semilla real del Excel congelado (PRD M1, Kimi M-02)."""

import pytest
from app.domain.rubro import (
    SEMILLA_RUBROS,
    Rubro,
    RubroGrupo,
    TipoFlujo,
)
from pydantic import ValidationError

GRUPOS = {
    "costo_producto",
    "operacion",
    "nomina",
    "deudas_obligaciones",
    "otros",
}


def test_grupos_son_los_cinco_del_prd():
    assert {g.value for g in RubroGrupo} == GRUPOS


def test_rubro_valido():
    r = Rubro(grupo="operacion", nombre="Arriendos", tipo_flujo="egreso", orden=4)
    assert r.grupo is RubroGrupo.OPERACION
    assert r.tipo_flujo is TipoFlujo.EGRESO
    assert r.activo is True and r.es_sistema is False


def test_strict_rechaza_campo_extra():
    with pytest.raises(ValidationError):
        Rubro(grupo="otros", nombre="X", orden=1, inventado=1)


def test_nombre_max_80():
    with pytest.raises(ValidationError):
        Rubro(grupo="otros", nombre="x" * 81, orden=1)


# ---- Semilla real (frozen: Flujo de pagos deudas.xlsx, hoja 'Presupuesto') ----


def test_semilla_tiene_33_rubros():
    # 31 categorías del Excel + 'Ajuste de conciliación' (Spec §2.2.6) + 'Recaudo'
    # (ingreso, Kimi B-1 / S0B-05: destino de los abonos de cuotas, PRD M7)
    assert len(SEMILLA_RUBROS) == 33


def test_semilla_cubre_los_cinco_grupos():
    assert {r["grupo"] for r in SEMILLA_RUBROS} == GRUPOS


def test_semilla_tres_rubros_de_sistema():
    sistema = [r["nombre"] for r in SEMILLA_RUBROS if r["es_sistema"]]
    assert set(sistema) == {"Por clasificar", "Ajuste de conciliación", "Recaudo"}


def test_semilla_unico_ingreso_es_recaudo():
    # Kimi B-1: la regla PRD M7 ('Abono' → ingreso recaudo) necesita rubro destino.
    ingresos = [r["nombre"] for r in SEMILLA_RUBROS if r["tipo_flujo"] == "ingreso"]
    assert ingresos == ["Recaudo"]


def test_semilla_nombres_unicos_por_grupo():
    vistos = set()
    for r in SEMILLA_RUBROS:
        clave = (r["grupo"], r["nombre"])
        assert clave not in vistos, f"duplicado {clave}"
        vistos.add(clave)


def test_semilla_ordenes_unicos_y_consecutivos():
    ordenes = sorted(r["orden"] for r in SEMILLA_RUBROS)
    assert ordenes == list(range(1, 34))


def test_semilla_construye_modelos_validos():
    for r in SEMILLA_RUBROS:
        Rubro(**r)  # no debe lanzar


def test_semilla_incluye_categorias_reales_conocidas():
    nombres = {r["nombre"] for r in SEMILLA_RUBROS}
    for esperado in (
        "Producto",
        "SOAT/Matrículas",
        "Seguros (Hunter)",
        "Transporte/peajes/combustible/parqueo",
        "Sueldos directivos",
        "Préstamos",
        "Impuestos",
    ):
        assert esperado in nombres, esperado
