# SOLICITUD de auditoría Kimi — FABS inc3 Pieza A (verificación por concepto) · CÓDIGO

- **Target:** PR (código) · **Ronda:** I (inicial) · **Umbral: ≥ 9.0**
- **Rama:** `feat/fabs-inc3a-concepto` · **Rango:** `61ded9c..6de54ef`
- **Fecha:** 2026-08-17 · **Solicita:** Andrés (CEO) / Claude
- **Gate de DISEÑO ya aprobado por Kimi: 9.3 GO** (este es el gate de CÓDIGO).
- **Por qué gate (crítico):** modifica el **control anti-alucinación del núcleo** de FABS. Flag `CFO_ENABLED` **apagado** (exposición cero).

## Qué es (una línea)

Cierra el hueco vinculante de inc2 (el verificador exigía evidencia **por unidad**, y caja e IVA son ambos COP → el modelo podía atribuir a "caja" el valor del IVA y pasaba) **quitándole al modelo la posibilidad de escribir un número**: el modelo **cita conceptos** con tokens `[[caja_hoy]]`; el **servicio sustituye** cada token por el valor concept-bound correcto; el verificador **prohíbe cifras crudas**. El mislabel es **imposible por construcción**.

## Qué hace, con evidencia verificada al peso

1. **El modelo ya NO ve el `valor`** (`tools.resultado_a_dict` → `{concepto, disponible, unidad, evidencia}`, sin `valor` ni `detalle`). Sin valores no puede fabricar, mal-etiquetar ni calcular.
2. **Cita por token** `[[caja_hoy]]`/`[[runway]]`/`[[iva_cuatrimestre]]` (prompt); solo conceptos disponibles ESTE turno.
3. **Verificador nuevo contrato** (`verificador.verificar`): CUALQUIER cifra cruda (COP/meses/%) → violación; token de concepto no disponible → violación. `ok = sin crudas ∧ tokens válidos`.
4. **Servicio: verificar → sustituir** (orden crítico). Tras verificar OK, `sustituir_tokens` reemplaza cada token por su valor concept-bound formateado; el texto sustituido (con valores) **nunca se re-verifica**. Tope: 1 reintento correctivo (da tokens, no valores) → reincidencia = abstención `motivo="verificacion"`, jamás loop.
5. **D-1 (interpretación server-bound):** `[[iva_cuatrimestre]]` → "$36.204.698 (vence el 2026-09-10, **en 24 días**)"; `[[runway]]` → "4,2 meses" (duración). El juicio de magnitud vs umbral queda declarado NO-alcance (requiere mínimo configurable).
6. **RE_TOKEN una sola definición compartida** (conceptos.py, importada en verificador) + tolerante a espacios → validar y sustituir usan el MISMO regex (drift imposible).

## Puntos a auditar con lupa

- **Propiedad anti-alucinación end-to-end:** ¿algún camino por el que una cifra fabricada o mal-etiquetada llegue al usuario con `abstuvo=False`? El caso caja/IVA de inc2 debe ser imposible.
- **Orden verify→sustituir** en toda rama (feliz y reintento); el texto sustituido nunca se re-verifica.
- **Decimal en todo** (regla 1); `_money_es` usa `int(Decimal)`, `_meses_es` usa `Decimal.__format__` — cero float.
- **D-1 vence_en_dias:** de la fecha DIAN real (`iva.py` `proximo_pago.fecha`), signo correcto, fallback sin fecha.
- **Flag-off = COMPAS idéntico:** el cambio (no-valor) solo afecta el agente tras el flag; `motor.py` 0 diffs; S1 intacto; `app/cfo/calc/*` sin cambios.

## Evidencia local (verde)

- **Suite backend completa: 1044 passed / 95 skipped / 0 failed** con el flag apagado (COMPAS idéntico).
- Núcleo `tests/cfo/agente/` verificador+conceptos+servicio: **34 passed**; `tests/cfo/` **82 passed**.
- `python -m ruff check app/cfo/` limpio. `motor.py` **cero diffs** (`git diff 61ded9c..6de54ef -- motor.py` vacío).
- **Review final whole-branch (opus): "Ready to merge — Yes", CERO Critical/Important.** Construido por SDD (subagente + review de dos etapas por tarea + fix waves).

## Alcance / no-alcance

- **Entra:** el contrato de citación por concepto (5 archivos del núcleo + `conceptos.py`) + tests. Solo los 3 conceptos actuales.
- **NO entra:** canal Telegram/hilos/vínculo (Pieza B), encender el flag (go-live), juicio de magnitud vs umbral (tool futura). `motor.py`/`calc/*` sin cambios.
- **Huecos residuales declarados (radar del piloto, aceptados):** aritmética en prosa ("el doble"), enteros pelados <5 díg sin separador, números en palabras — no los caza el regex (mitigación = prompt regla #1 + abstención).

## Pregunta al auditor

¿El contrato de citación por concepto cierra el hueco caja/IVA de forma sólida y segura? ¿Algún camino por el que una cifra fabricada o mal-etiquetada se publique? ¿Listo para merge (flag apagado) y para que la Pieza B (Telegram) construya encima?
