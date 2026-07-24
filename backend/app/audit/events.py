# backend/app/audit/events.py
"""Catálogo CERRADO de eventos de auditoría (regla 11 / Spec §1.11 / CR-001 /
CR-S2 / CR-S4 / CR-S5 / CR-S6).

29 del Spec §1.11 (10 v1.0 + 12 v1.1 + 7 v1.1.1) + `extracto.cargado` (CR-001)
+ `transaccion.creada` (CR-S2 — Kimi M-1 sprint2-cargas: rastro forense permanente
del POST manual, la única vía de dinero sin archivo de banco)
+ `rubro.creado`/`rubro.editado` (CR-S4 — C1 categorías administrables, GO Kimi
PLAN-I 9.2; `rubro.desactivado` ya venía en v1.0, por eso CR-S4 es +2)
+ `regla.creada`/`regla.editada`/`regla.desactivada` (CR-S5 — C3
auto-clasificación, GO Kimi PLAN-I 9.3; la aprobación de aprendidas emite
`regla.editada` {activa: false→true, via: 'aprobacion'} — sin evento extra)
+ `saldo_banco.reportado` (CR-S6 — C4 ajuste diario de caja, GO Kimi PLAN-I 9.3;
un evento POR BANCO tocado, metadata con valores y fechas anterior→nuevo)
+ `pago_planeado.creado`/`editado`/`cancelado` (CR-S7 — C9 pagos de la semana, GO
CEO 2026-07-23 con Kimi retroactivo; `marcar-pagado` reusa `pago_planeado.editado`
{estado: pendiente→pagado} — sin evento extra) = 40.
+ `modelo_moto.creado`/`editado`/`desactivado` + `parametros_proyeccion.actualizado`
(CR-COCK — COCK-01/02 motor de proyección C7, GO CEO 2026-07-23 con Kimi retroactivo;
la reactivación de un modelo reusa `modelo_moto.editado` {activo: false→true}) = 44.
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

    # ── CR-001 (1) ──
    extracto_cargado = "extracto.cargado"

    # ── CR-S2 (1) ──
    transaccion_creada = "transaccion.creada"

    # ── CR-S4 (2) — C1 categorías administrables ──
    rubro_creado = "rubro.creado"
    rubro_editado = "rubro.editado"

    # ── CR-S5 (3) (C3 auto-clasificación) ──
    regla_creada = "regla.creada"
    regla_editada = "regla.editada"
    regla_desactivada = "regla.desactivada"

    # ── CR-S6 (1) (C4 ajuste diario de caja) ──
    saldo_banco_reportado = "saldo_banco.reportado"

    # ── CR-S7 (3) (C9 pagos de la semana) ──
    pago_planeado_creado = "pago_planeado.creado"
    pago_planeado_editado = "pago_planeado.editado"
    pago_planeado_cancelado = "pago_planeado.cancelado"

    # ── CR-COCK (4) → total 44 (C7 motor de proyección) ──
    modelo_moto_creado = "modelo_moto.creado"
    modelo_moto_editado = "modelo_moto.editado"
    modelo_moto_desactivado = "modelo_moto.desactivado"
    parametros_proyeccion_actualizado = "parametros_proyeccion.actualizado"


# Conjunto de los 40 valores canónicos (para validación/tests de completitud).
CATALOGO_EVENTOS: frozenset[str] = frozenset(e.value for e in AuditEvento)
