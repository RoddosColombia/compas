# RESPUESTA KIMI — sprint4-cierre-conciliacion · I-PLAN

**Resultado:** **NO-GO condicionado — 8.5 / 10** (umbral ≥ 9.0) · **Fecha:** 2026-07-21
**PDF fuente:** `COMPAS_Auditoria_I-PLAN_Sprint4_Cierre_2026-07-21.footnote.docx`
**Camino:** incorporar M-1..M-4 (~medio día de precisión) → re-presentar ronda R (mismo día). Estimación tras ajustes: ≥ 9.4.

Diseño general sólido (saga O1, RBAC §2.4, ajuste en M+1 nunca en el mes cerrado, umbral ≤ absorbe / > bloquea). 4 hallazgos que tocan el núcleo aritmético:

## Hallazgos

- **M-1 (Media) — `definido → en_ejecucion` no existe.** La aprobación (Sprint 3) deja el mes en `definido`; nada lo mueve a `en_ejecucion` (US-02: "el mes pasa a en_ejecucion"). Tal cual, la reapertura sería la primera vía que llega a ese estado — al revés del ciclo. **Rec:** la aprobación pone el mes directo en `en_ejecucion` (con definido_por/at + evento `presupuesto.definido` como registro → resuelve D1 sin evento nuevo).

- **M-2 (Media, núcleo) — la aritmética de conciliación/ancla (F-14) no cierra.** El ajuste se calcula (R_M − C_M), pero M+1 se abre ANTES del cierre de M con ancla R_open → `R_open + (R_M − C_M) ≠ R_M` salvo coincidencia. **Corrección:** dentro de la transacción multi-doc del cierre, **re-fijar `saldo_inicial(M+1) := R_M`** (sancionado por §1.3/F-14), guardando el valor previo para la reversión; **definir la regla anti-doble-conteo** (¿el ajuste entra o no en la caja disponible de M+1?) + **prueba numérica que cuadre**.

- **M-3 (Media-Baja) — conciliación por banco necesita ancla POR BANCO:** último saldo reportado del banco (a su `fecha_reporte`) + movimientos de ESE banco posteriores — no el `saldo_inicial_caja` consolidado. Banco sin saldo reportado → **"sin dato"** (regla 7), nunca comparar contra 0.

- **M-4 (Media-Baja) — la reversión del ajuste al reabrir debe ser CONTRA-ASIENTO, nunca DELETE.** La Transaccion es inmutable por dato (§2.2.2). Contra-asiento signo invertido, mismo |valor|, metadata `{revierte: id_ajuste_original}`, dentro de la transacción de reapertura + **restaurar el ancla previa** guardada en el cierre.

## Camino
M-1 aprobación→en_ejecucion · M-2 re-anclar + regla anti-doble-conteo + ejemplo numérico · M-3 ancla por banco + "sin dato" · M-4 contra-asiento en reapertura. Re-presentación → verificación mismo día, estimación ≥ 9.4.
