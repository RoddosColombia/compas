# backend/tests/test_audit_events.py
"""Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001 / CR-S2 /
CR-S4 / CR-S5 / CR-S6.

29 (Spec §1.11) + extracto.cargado (CR-001) + transaccion.creada (CR-S2, Kimi
M-1 sprint2-cargas) + rubro.creado/rubro.editado (CR-S4, C1 categorías
administrables — `rubro.desactivado` ya venía en v1.0) +
regla.creada/regla.editada/regla.desactivada (CR-S5, C3 auto-clasificación,
GO Kimi PLAN-I 9.3) + saldo_banco.reportado (CR-S6, C4 ajuste diario de caja,
GO Kimi PLAN-I 9.3) + pago_planeado.creado/editado/cancelado (CR-S7, C9 pagos
de la semana, GO CEO 2026-07-23) = 40. No se inventan eventos sin CR."""

from app.audit.events import CATALOGO_EVENTOS, AuditEvento


def test_catalogo_tiene_exactamente_40_eventos():
    assert len(AuditEvento) == 40
    assert len(CATALOGO_EVENTOS) == 40


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
        "transaccion.creada",  # CR-S2 (Kimi M-1): rastro forense del POST manual
        "rubro.creado",  # CR-S4 (C1): alta de categoría desde la app
        "rubro.editado",  # CR-S4 (C1): edición (incl. reactivación B-3)
        "rubro.desactivado",  # v1.0: baja lógica (verificado Kimi PLAN-I C1)
        "regla.creada",  # CR-S5 (C3): alta de regla de clasificación
        "regla.editada",  # CR-S5 (C3): edición/reactivación/aprobación
        "regla.desactivada",  # CR-S5 (C3): baja lógica de regla
        "saldo_banco.reportado",  # CR-S6 (C4): reporte diario de saldo por banco
        "pago_planeado.creado",  # CR-S7 (C9): alta de pago programado
        "pago_planeado.editado",  # CR-S7 (C9): edición/marcar-pagado
        "pago_planeado.cancelado",  # CR-S7 (C9): baja lógica del pago
    ):
        assert esperado in CATALOGO_EVENTOS


def test_valores_son_dominio_punto_accion():
    # Convención: "<dominio>.<acción>" en minúsculas.
    for e in AuditEvento:
        assert "." in e.value
        assert e.value == e.value.lower()
