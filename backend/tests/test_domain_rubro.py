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


# ---- Semilla real (contrato: docs/modelo/MODELO.md, 'Base real egresos') ----


def test_semilla_tiene_34_rubros():
    # 31 categorías reales de MODELO.md + los 3 de sistema ('Por clasificar',
    # 'Ajuste de conciliación' Spec §2.2.6, 'Recaudo' ingreso Kimi B-1/S0B-05).
    # Re-seed C1 (GO Kimi PLAN-I 9.2): la taxonomía manda MODELO.md.
    assert len(SEMILLA_RUBROS) == 34


def test_semilla_reparto_por_grupo_segun_modelo():
    # MODELO.md: costo 3 · operación 13 · nómina 5 · deudas 3 · otros 7 (+3 sistema).
    conteo: dict[str, int] = {}
    for r in SEMILLA_RUBROS:
        conteo[r["grupo"]] = conteo.get(r["grupo"], 0) + 1
    assert conteo == {
        "costo_producto": 3,
        "operacion": 13,
        "nomina": 5,
        "deudas_obligaciones": 3,
        "otros": 10,  # 7 reales + 3 de sistema
    }


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
    assert ordenes == list(range(1, 35))


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
        # Nuevas de MODELO.md ('Base real egresos') — re-seed C1:
        "Viajes corporativos",
        "Grúas y traslados",
        "Dotación empleados",
        "Freelance",
        "Asuntos legales",
    ):
        assert esperado in nombres, esperado


def test_semilla_arriendos_vive_en_otros():
    # MODELO.md ubica 'Arriendos' en OTROS (la semilla vieja lo tenía en operación;
    # el doc viejo NO se toca — D3: el CEO depura desde la app).
    arriendos = [r for r in SEMILLA_RUBROS if r["nombre"] == "Arriendos"]
    assert [r["grupo"] for r in arriendos] == ["otros"]
