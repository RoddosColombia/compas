# backend/app/audit/events.py
"""Catálogo CERRADO de eventos de auditoría (regla 11 / Spec §1.11 / CR-001).

29 del Spec §1.11 (10 v1.0 + 12 v1.1 + 7 v1.1.1) + `extracto.cargado` (CR-001) = 30.
NO se inventan eventos sin CR. El nombre del miembro usa `_`; el valor usa
`<dominio>.<acción>`."""

from enum import StrEnum


class AuditEvento(StrEnum):
    # ── v1.0 (10) ──
    presupuesto_acotado = "presupuesto.acotado"
    presupuesto_definido = "presupuesto.definido"
    mes_cerrado = "mes.cerrado"
    mes_reabierto = "mes.reabierto"
    transaccion_clasificada = "transaccion.clasificada"
    carga_completada = "carga.completada"
    factura_creada = "factura.creada"
    iva_declarado = "iva.declarado"
    rubro_desactivado = "rubro.desactivado"
    user_login = "user.login"

    # ── v1.1 (12) ──
    mes_creado = "mes.creado"
    user_login_fallido = "user.login_fallido"
    user_bloqueado = "user.bloqueado"
    user_creado = "user.creado"
    user_rol_cambiado = "user.rol_cambiado"
    user_desactivado = "user.desactivado"
    exportacion_realizada = "exportacion.realizada"
    archivo_descargado = "archivo.descargado"
    config_actualizada = "config.actualizada"
    parametros_ingreso_modificado = "parametros_ingreso.modificado"
    saldo_inicial_editado = "saldo_inicial.editado"
    carga_fallida = "carga.fallida"

    # ── v1.1.1 (7) ──
    presupuesto_crec_modificado = "presupuesto.crec_modificado"
    presupuesto_crec_global_aplicado = "presupuesto.crec_global_aplicado"
    iva_generado_override = "iva_generado.override"
    transaccion_tardia = "transaccion.tardia"
    factura_emitida_creada = "factura_emitida.creada"
    factura_emitida_editada = "factura_emitida.editada"
    factura_emitida_anulada = "factura_emitida.anulada"

    # ── CR-001 (1) → total 30 ──
    extracto_cargado = "extracto.cargado"


# Conjunto de los 30 valores canónicos (para validación/tests de completitud).
CATALOGO_EVENTOS: frozenset[str] = frozenset(e.value for e in AuditEvento)
