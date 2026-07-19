# backend/tests/test_audit_events.py
"""Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001.

29 (Spec §1.11) + extracto.cargado (CR-001) = 30. No se inventan eventos."""

from app.audit.events import CATALOGO_EVENTOS, AuditEvento


def test_catalogo_tiene_exactamente_30_eventos():
    assert len(AuditEvento) == 30
    assert len(CATALOGO_EVENTOS) == 30


def test_extracto_cargado_es_el_evento_30_de_cr001():
    # CR-001: extracto.cargado (extracto mensual) != carga.completada (carga diaria).
    assert AuditEvento.extracto_cargado.value == "extracto.cargado"
    assert AuditEvento.carga_completada.value == "carga.completada"
    assert AuditEvento.extracto_cargado != AuditEvento.carga_completada


def test_eventos_clave_presentes():
    for esperado in (
        "user.login",
        "user.login_fallido",
        "user.bloqueado",
        "mes.cerrado",
        "presupuesto.definido",
        "iva_generado.override",
        "factura_emitida.anulada",
    ):
        assert esperado in CATALOGO_EVENTOS


def test_valores_son_dominio_punto_accion():
    # Convención: "<dominio>.<acción>" en minúsculas.
    for e in AuditEvento:
        assert "." in e.value
        assert e.value == e.value.lower()
