# backend/tests/test_domain_rubro.py
"""Rubro (Spec §1.2) + plan de cuentas de ARQUITECTURA_PRESUPUESTAL.md.

Estructura del archivo de Arquitectura (3 niveles, código, Fijo/Variable, 6 grupos)
+ taxonomía real de 'Base real egresos'/'Proyeccion ingresos' (archivo de deudas)."""

import pytest
from app.domain.rubro import (
    SEMILLA_RUBROS,
    Rubro,
    RubroGrupo,
    TipoFlujo,
    TipoRubro,
)
from pydantic import ValidationError

GRUPOS = {
    "ingresos_operativos",
    "costo_producto",
    "operacion",
    "nomina",
    "deudas_obligaciones",
    "otros",
}


def test_grupos_son_los_seis_del_plan_de_cuentas():
    # 6 grupos: 0000 ingresos, 1000 costo, 2000 operación, 3000 nómina,
    # 4000 deudas, 5000 otros.
    assert {g.value for g in RubroGrupo} == GRUPOS
    # ingresos operativos es el PRIMERO (código 0000)
    assert list(RubroGrupo)[0] is RubroGrupo.INGRESOS_OPERATIVOS


def test_rubro_valido_con_codigo_y_tipo():
    r = Rubro(
        grupo="operacion",
        nombre="Arriendos",
        tipo_flujo="egreso",
        codigo="2010",
        tipo="fijo",
        orden=4,
    )
    assert r.grupo is RubroGrupo.OPERACION
    assert r.tipo_flujo is TipoFlujo.EGRESO
    assert r.tipo is TipoRubro.FIJO
    assert r.codigo == "2010"
    assert r.activo is True and r.es_sistema is False


def test_tipo_y_codigo_opcionales():
    # los rubros de sistema / construcciones simples no exigen tipo ni código
    r = Rubro(grupo="otros", nombre="Ajuste de conciliación", orden=1)
    assert r.tipo is None and r.codigo is None


def test_strict_rechaza_campo_extra():
    with pytest.raises(ValidationError):
        Rubro(grupo="otros", nombre="X", orden=1, inventado=1)


def test_nombre_max_80():
    with pytest.raises(ValidationError):
        Rubro(grupo="otros", nombre="x" * 81, orden=1)


# ---- Plan de cuentas (contrato: docs/modelo/ARQUITECTURA_PRESUPUESTAL.md) ----


def test_semilla_tiene_42_rubros():
    # 4 ingresos + 3 costo + 14 operación + 7 nómina + 6 deudas + 7 otros
    # + 'Ajuste de conciliación' (sistema, sin código) = 42.
    assert len(SEMILLA_RUBROS) == 42


def test_semilla_reparto_por_grupo():
    conteo: dict[str, int] = {}
    for r in SEMILLA_RUBROS:
        conteo[r["grupo"]] = conteo.get(r["grupo"], 0) + 1
    assert conteo == {
        "ingresos_operativos": 4,
        "costo_producto": 3,
        "operacion": 14,
        "nomina": 7,
        "deudas_obligaciones": 6,
        "otros": 8,  # 7 reales (incl. 5070 Por clasificar) + Ajuste de conciliación
    }


def test_semilla_cubre_los_seis_grupos():
    assert {r["grupo"] for r in SEMILLA_RUBROS} == GRUPOS


def test_semilla_rubros_de_sistema():
    sistema = {r["nombre"] for r in SEMILLA_RUBROS if r["es_sistema"]}
    assert sistema == {"Recaudo de cartera", "Por clasificar", "Ajuste de conciliación"}


def test_semilla_ingresos_son_del_grupo_0000():
    ingresos = [r for r in SEMILLA_RUBROS if r["tipo_flujo"] == "ingreso"]
    assert {r["nombre"] for r in ingresos} == {
        "Recaudo de cartera",
        "Cuotas iniciales",
        "RODANTE (crédito de repuestos)",
        "Otros ingresos",
    }
    assert all(r["grupo"] == "ingresos_operativos" for r in ingresos)


def test_semilla_recaudo_de_cartera_es_sistema_e_ingreso():
    # destino de la regla 'Abono'/'Recibido de' de C3 (reemplaza al viejo 'Recaudo')
    rec = [r for r in SEMILLA_RUBROS if r["nombre"] == "Recaudo de cartera"]
    assert len(rec) == 1
    assert rec[0]["es_sistema"] is True
    assert rec[0]["tipo_flujo"] == "ingreso"
    assert rec[0]["codigo"] == "0110"


def test_semilla_codigos_unicos_donde_existen():
    codigos = [r["codigo"] for r in SEMILLA_RUBROS if r["codigo"] is not None]
    assert len(codigos) == len(set(codigos))  # sin duplicados
    assert "2010" in codigos and "0110" in codigos and "5070" in codigos


def test_semilla_tipo_fijo_o_variable_en_los_reales():
    # todo rubro con código (del plan de cuentas) tiene Fijo o Variable
    for r in SEMILLA_RUBROS:
        if r["codigo"] is not None:
            assert r["tipo"] in ("fijo", "variable"), r["nombre"]


def test_semilla_nombres_unicos_por_grupo():
    vistos = set()
    for r in SEMILLA_RUBROS:
        clave = (r["grupo"], r["nombre"])
        assert clave not in vistos, f"duplicado {clave}"
        vistos.add(clave)


def test_semilla_ordenes_unicos_y_consecutivos():
    ordenes = sorted(r["orden"] for r in SEMILLA_RUBROS)
    assert ordenes == list(range(1, 43))


def test_semilla_construye_modelos_validos():
    for r in SEMILLA_RUBROS:
        Rubro(**r)  # no debe lanzar


def test_semilla_arriendos_vive_en_operacion():
    # ARQUITECTURA_PRESUPUESTAL: Arriendos es 2010 (Operación, Fijo).
    arriendos = [r for r in SEMILLA_RUBROS if r["nombre"] == "Arriendos"]
    assert len(arriendos) == 1
    assert arriendos[0]["grupo"] == "operacion"
    assert arriendos[0]["codigo"] == "2010"
    assert arriendos[0]["tipo"] == "fijo"


def test_semilla_dotacion_vive_en_nomina():
    # reubicado a Nómina 3050 (antes estaba en Operación).
    dot = [r for r in SEMILLA_RUBROS if r["nombre"] == "Dotación empleados"]
    assert dot[0]["grupo"] == "nomina" and dot[0]["codigo"] == "3050"


def test_semilla_incluye_rubros_nuevos_de_la_arquitectura():
    nombres = {r["nombre"] for r in SEMILLA_RUBROS}
    for esperado in (
        "RODANTE (crédito de repuestos)",
        "Cuotas iniciales",
        "Garantía cupo (Auteco)",
        "Deudas impuestos",
        "Inventario Auteco (150 días)",
        "Planillas nuevas",
        "Grúas y traslados",
        "Freelance",
    ):
        assert esperado in nombres, esperado
