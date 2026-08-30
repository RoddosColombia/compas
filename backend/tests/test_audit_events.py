# backend/tests/test_audit_events.py
"""Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001 / CR-S2 /
CR-S4 / CR-S5 / CR-S6.

29 (Spec §1.11) + extracto.cargado (CR-001) + transaccion.creada (CR-S2, Kimi
M-1 sprint2-cargas) + rubro.creado/rubro.editado (CR-S4, C1 categorías
administrables — `rubro.desactivado` ya venía en v1.0) +
regla.creada/regla.editada/regla.desactivada (CR-S5, C3 auto-clasificación,
GO Kimi PLAN-I 9.3) + saldo_banco.reportado (CR-S6, C4 ajuste diario de caja,
GO Kimi PLAN-I 9.3) + pago_planeado.creado/editado/cancelado (CR-S7, C9 pagos
de la semana, GO CEO 2026-07-23) + modelo_moto.creado/editado/desactivado +
parametros_proyeccion.actualizado (CR-COCK, C7 motor de proyección, GO CEO
2026-07-23) = 44. No se inventan eventos sin CR.

vigilante.paquete.generado/publicado (CR-CFO-3, FABS vigilante paquete lunes,
GO CEO 2026-08-30) llevan el catálogo a 68 (ver test abajo)."""

from app.audit.events import CATALOGO_EVENTOS, AuditEvento


def test_catalogo_tiene_exactamente_68_eventos():
    # 59 + factura_obligacion.pagada (D2 §7, GO CEO 2026-08-04)
    # + transaccion.dividida + transaccion.division_deshecha (PTS6-B, CR división de
    #   clasificación, GO CEO 2026-08-10) = 62
    # + cfo.consulta + cfo.respuesta (CR-CFO-1, FABS incremento 2,
    #   GO CEO 2026-08-11) = 64
    # + cfo.vinculo_creado + cfo.vinculo_eliminado (CR-CFO-2, FABS inc3 Pieza B —
    #   canal Telegram, GO CEO 2026-08-17) = 66.
    # + vigilante.paquete.generado + vigilante.paquete.publicado (CR-CFO-3, FABS
    #   vigilante paquete lunes, GO CEO 2026-08-30) = 68.
    assert len(AuditEvento) == 68
    assert len(CATALOGO_EVENTOS) == 68
    assert AuditEvento.factura_actualizada.value == "factura.actualizada"
    assert AuditEvento.factura_obligacion_pagada.value == "factura_obligacion.pagada"
    assert AuditEvento.transaccion_dividida.value == "transaccion.dividida"
    assert (
        AuditEvento.transaccion_division_deshecha.value
        == "transaccion.division_deshecha"
    )
    assert "cfo.consulta" in CATALOGO_EVENTOS
    assert "cfo.respuesta" in CATALOGO_EVENTOS
    assert "cfo.vinculo_creado" in CATALOGO_EVENTOS
    assert "cfo.vinculo_eliminado" in CATALOGO_EVENTOS
    assert "vigilante.paquete.generado" in CATALOGO_EVENTOS
    assert "vigilante.paquete.publicado" in CATALOGO_EVENTOS


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
        "modelo_moto.creado",  # CR-COCK (C7): alta de modelo de moto
        "modelo_moto.editado",  # CR-COCK (C7): edición/reactivación
        "modelo_moto.desactivado",  # CR-COCK (C7): baja lógica del modelo
        "parametros_proyeccion.actualizado",  # CR-COCK (C7): drivers del motor
        "cartera_previa.cargada",  # CR Fidelidad (PR-1): seed serie cartera previa
        "factura.creada",  # v1.0 / CR Fidelidad (PR-2a): carga de factura para IVA
        "factura.anulada",  # CR Fidelidad (PR-2a): baja lógica de factura cargada
        "loantape.cargado",  # aging SISMO-V3: carga del LoanTape semanal
        "escenario_impacto.creado",  # CR-D1: guardar escenario what-if
        "escenario_impacto.editado",  # CR-D1: editar/reactivar escenario
        "escenario_impacto.eliminado",  # CR-D1: baja lógica de escenario
        "obligacion.creada",  # CR-D2: alta de obligación
        "obligacion.editada",  # CR-D2: edición/reactivación
        "obligacion.eliminada",  # CR-D2: baja lógica
        "factura_obligacion.registrada",  # CR-D2: registro de factura
        "factura_obligacion.anulada",  # CR-D2: anulación de factura
        "meta_ingreso.creada",  # CR-D2: alta de meta de ingreso
        "meta_ingreso.editada",  # CR-D2: edición de meta
        "meta_ingreso.eliminada",  # CR-D2: baja lógica de meta
        "vigilante.paquete.generado",  # CR-CFO-3: job arma el borrador semanal
        "vigilante.paquete.publicado",  # CR-CFO-3: revisor difunde al comité
    ):
        assert esperado in CATALOGO_EVENTOS


def test_valores_son_dominio_punto_accion():
    # Convención: "<dominio>.<acción>" en minúsculas.
    for e in AuditEvento:
        assert "." in e.value
        assert e.value == e.value.lower()
