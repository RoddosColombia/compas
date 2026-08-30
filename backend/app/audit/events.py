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

    # PTS6-B (CR división de clasificación, GO CEO 2026-08-10): una transacción
    # bancaria que cubre varios conceptos se reparte en partes que suman exacto su
    # valor. Los inmutables §2.2 no cambian; el rastro queda completo y es reversible.
    transaccion_dividida = "transaccion.dividida"
    transaccion_division_deshecha = "transaccion.division_deshecha"

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
    # CR "Fidelidad de caja" (PR-1): seed de la serie de cartera previa (44 -> 45).
    cartera_previa_cargada = "cartera_previa.cargada"
    # CR "Fidelidad de caja" (PR-2a, C11): baja lógica de una factura cargada para IVA
    # (par de `factura.creada`, ya en v1.0). `factura_emitida.anulada` es SOLO para la
    # emisión de ventas; esta cubre compras+ventas cargadas al liquidador (45 -> 46).
    factura_anulada = "factura.anulada"
    # CR-E2-EDITAR (PR2): edición de los campos NO fiscales de una factura de IVA
    # (deducible/origen) vía PATCH. Marcar deducibilidad cambia el IVA a pagar -> autor
    # obligatorio (R3). Un evento por factura tocada; metadata sin PII. Catálogo 58->59.
    factura_actualizada = "factura.actualizada"
    # Aging SISMO-V3: carga del LoanTape semanal (snapshot por crédito) para mora por
    # tramo + proyección crédito a crédito (46 -> 47).
    loantape_cargado = "loantape.cargado"
    # CR-D1 (3) — escenarios de impacto nombrados con CRUD auditado (D1 §2, GO CEO
    # 2026-07-27). Guardar/editar/eliminar un escenario what-if; simular NO audita
    # (47 -> 50). Reactivar reusa `escenario_impacto.editado` {activo false->true}.
    escenario_impacto_creado = "escenario_impacto.creado"
    escenario_impacto_editado = "escenario_impacto.editado"
    escenario_impacto_eliminado = "escenario_impacto.eliminado"
    # CR-D2 (8) — obligaciones, facturas y metas de ingreso (D2 §2/§6, GO CEO
    # 2026-07-27). CRUD auditado de tres entidades; simular (política §5) NO audita
    # (50 -> 58). Bajas lógicas; reactivar reusa `.editada` {activo false->true}.
    obligacion_creada = "obligacion.creada"
    obligacion_editada = "obligacion.editada"
    obligacion_eliminada = "obligacion.eliminada"
    factura_obligacion_registrada = "factura_obligacion.registrada"
    factura_obligacion_anulada = "factura_obligacion.anulada"
    # D2 §7 (GO CEO 2026-08-04): pago de una factura con distinción de origen
    # (roddos = sale de caja / tercero = baja deuda sin tocar caja). La anulación del
    # pago REUSA este evento con metadata {via: 'anulacion'} (espejo de regla.editada),
    # sin evento extra. Catálogo 59 -> 60.
    factura_obligacion_pagada = "factura_obligacion.pagada"
    meta_ingreso_creada = "meta_ingreso.creada"
    meta_ingreso_editada = "meta_ingreso.editada"
    meta_ingreso_eliminada = "meta_ingreso.eliminada"

    # ── CR-CFO-1 (2) — FABS incremento 2 (agente CFO, GO CEO 2026-08-11) ──
    # Rastro forense de cada interacción con FABS (lectura/asesoría; no mueve plata).
    # `cfo.consulta` = pregunta recibida (actor_id = usuario real); `cfo.respuesta` =
    # lo que FABS respondió, con {abstuvo, motivo, conceptos_usados, cifras+evidencia,
    # uso}. La abstención es un `cfo.respuesta` {abstuvo: true} — sin evento extra.
    # Catálogo 62 -> 64.
    cfo_consulta = "cfo.consulta"
    cfo_respuesta = "cfo.respuesta"

    # ── CR-CFO-2 (2) — FABS inc3 Pieza B (canal Telegram, GO CEO 2026-08-17) ──
    # Alta/baja del vínculo telegram_id↔user_id (allowlist, solo admin). El Q&A por
    # Telegram REUSA cfo.consulta/cfo.respuesta con metadata.canal="telegram" — sin
    # eventos nuevos para eso. Catálogo 64 -> 66.
    cfo_vinculo_creado = "cfo.vinculo_creado"
    cfo_vinculo_eliminado = "cfo.vinculo_eliminado"

    # ── CR-CFO-3 (2) — FABS vigilante paquete lunes (GO CEO 2026-08-30) ──
    # Proactivo: `vigilante.paquete.generado` = el job armó el borrador semanal
    # (metadata {semana, abstuvo, conceptos_usados}); `vigilante.paquete.publicado`
    # = el revisor lo difundió al comité vía "publicar" (metadata {semana,
    # n_destinatarios}). La generación también emite cfo.consulta/cfo.respuesta
    # (reusa consultar). Catálogo 66 -> 68.
    vigilante_paquete_generado = "vigilante.paquete.generado"
    vigilante_paquete_publicado = "vigilante.paquete.publicado"


# Conjunto de los valores canónicos del catálogo (para validación/tests de completitud).
CATALOGO_EVENTOS: frozenset[str] = frozenset(e.value for e in AuditEvento)
