# backend/tests/test_domain_regla.py
"""ReglaClasificacion (Spec §1.9, C3, GO Kimi PLAN-I 9.3) + normalización única.

La normalización compartida (case-insensitive + sin tildes) es EL punto delicado
de la pieza (Kimi §3): la misma función normaliza el patrón al escribir la regla y
la descripción al matchear — el test cubre tilde↔sin-tilde y case en AMBAS
direcciones."""

import pytest
from app.domain.regla_clasificacion import (
    OrigenRegla,
    ReglaClasificacion,
    coincide,
    normalizar_texto,
)
from beanie import PydanticObjectId
from pydantic import ValidationError

# ── Normalización única compartida (Kimi: test exigido, ambas direcciones) ──


def test_normalizar_case_y_tildes():
    assert normalizar_texto("Café") == "cafe"
    assert normalizar_texto("CAFETERÍA LA 14") == "cafeteria la 14"
    assert normalizar_texto("  Peaje  ") == "peaje"


def test_match_tilde_patron_contra_descripcion_sin_tilde():
    # Patrón "Café" matchea "CAFETERIA LA 14" (patrón con tilde, descripción sin).
    assert coincide("Café", "CAFETERIA LA 14")


def test_match_sin_tilde_patron_contra_descripcion_con_tilde():
    # Dirección inversa: patrón sin tilde matchea descripción con tilde.
    assert coincide("cafeteria", "Compra CAFETERÍA central")


def test_match_case_ambas_direcciones():
    assert coincide("PEAJE", "pago peaje ruta 40")
    assert coincide("peaje", "PAGO PEAJE RUTA 40")


def test_no_match():
    assert not coincide("gasolina", "CAFETERIA LA 14")


# ── Modelo (Spec §1.9) ──


def _regla(**over):
    base = {
        "patron": "Cafetería",
        "rubro_id": PydanticObjectId(),
        "tipo_flujo": "egreso",
        "prioridad": 10,
        "creada_por": "u1",
    }
    base.update(over)
    return ReglaClasificacion(**base)


def test_regla_valida_deriva_patron_normalizado():
    r = _regla()
    assert r.patron == "Cafetería"
    assert r.patron_normalizado == "cafeteria"
    assert r.origen is OrigenRegla.MANUAL
    assert r.activa is True


def test_patron_minimo_3_caracteres():
    # Guarda contra match-all (Kimi §3): 2 chars → inválido.
    with pytest.raises(ValidationError):
        _regla(patron="ab")


def test_patron_max_120():
    with pytest.raises(ValidationError):
        _regla(patron="x" * 121)


def test_strict_rechaza_campo_extra():
    with pytest.raises(ValidationError):
        _regla(inventado=1)


def test_origen_aprendida_valido():
    r = _regla(origen="aprendida", activa=False)
    assert r.origen is OrigenRegla.APRENDIDA
    assert r.activa is False
