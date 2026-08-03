# I-PLAN — CR-WAVA: Dinero en tránsito (Wava) en el cierre y la apertura de mes

> Transcripción fiel de `docs/COMPAS_IPLAN_CR-WAVA_Construccion_2026-08-03.pdf` (Kimi, arquitecto).
> Fuente autoritativa del build. **Fecha:** 2026-08-03 · **Arquitecto:** Kimi · **Ejecuta:** Claude Code
> · **Gate:** Kimi ≥9 (pre-merge, directo al repo).

**Contratos:** `docs/COMPAS_CR-Wava_Transito_Cierre.md` (Opción B, GO CEO 2026-08-01) + precisiones del
arquitecto (etapa47) + decisión CEO 2026-08-02: se construye **ANTES de E1** (reorden aprobado; julio se
cierra CON tránsito declarado).

**Reglas duras:** R0 `motor.py` cero diffs · golden sin regenerar · compuerta IVA intacta · **catálogo de
eventos NO crece** (tránsito plegado en `mes.cerrado`) · **cero permisos nuevos** · Decimal/string/Bogotá/
strict+forbid · TDD rojo→verde · migración idempotente con URI por env · **un solo PR**.

## 0. Decisiones ya tomadas (no rediscutir)
1. **Julio NO se cerró esta noche.** Se cierra cuando este módulo esté en producción, declarando
   `transito_wava = 37.280.415` (la cifra real del CEO). La NOTA de julio queda **superada y se enmienda**:
   julio ya no cierra "sin Wava" — cierra CON el tránsito declarado; los depósitos Wava-por-julio que
   aterricen en agosto se clasifican contra el rubro de tránsito (no son recaudo de agosto).
2. **La fórmula del CEO es el diseño:** caja = Bancos X · Tránsito Wava Y · Total X+Y, en **dos líneas
   nombradas**, nunca sumado dentro de un banco.
3. **Julio-2026 es el primer cierre con tránsito** → aplica la regla completa desde ese momento (remanente,
   aviso, clasificación al rubro).

## 1. Dominio y semilla
- `MesControl` gana `transito_wava: Money = 0` (strict+forbid; los docs existentes leen 0 por defecto — la
  "migración de datos" es un **no-op por construcción**, se verifica, no se escribe nada).
- Rubro de sistema **`Tránsito Wava mes anterior`**: `es_sistema=True`, `tipo_flujo=INGRESO`, grupo **OTROS**
  (mismo grupo que 'Ajuste de conciliación'), sin código de plan. Sembrado por migración idempotente
  (`$setOnInsert` por `(grupo, nombre)`, con reporte de colisión).
- El rubro **ya está en la lista blanca** del guard es_sistema (FIX-A) → la clasificación manual hacia él
  está permitida desde ya.

## 2. Exclusión del recaudo (P-1 — bloqueante de diseño)
- `metas_ingreso/service.py::ingreso_real`: excluir **por `rubro_id`** (NUNCA por grupo ni por `es_sistema`)
  los dos rubros neutros: **`Tránsito Wava mes anterior`** y **`Ajuste de conciliación`** (este último sanea
  el hueco preexistente: un contra-asiento INGRESO de reapertura hoy entra a `ingreso_real`).
- Tests: (a) tx al rubro tránsito no mueve `real_ejecutado`; (b) contra-asiento de reapertura tampoco;
  (c) una tx a 'Recaudo de cartera' SÍ lo mueve (regresión).

## 3. Captura en el cierre (P-2, P-3)
- `POST /meses/{mes}/cierre/confirmar` gana **body** Pydantic strict+forbid: `{transito_wava: str = "0"}`
  (decimal finito, ≥ 0). El **`request_hash` incluye el body completo** (`{"mes", "transito_wava"}`) — misma
  key con otro monto → **422**; mismo monto → **replay**.
- `confirmar_cierre(*, mes, usuario_id, transito_wava: Decimal = 0)`:
  - Persiste `mc.transito_wava = transito_wava` **dentro de la transacción `_cerrar`** (junto al re-anclaje
    R_M — intacto).
  - `mes.cerrado` metadata gana `transito_wava` (string). **Nada más cambia en la matemática certificada**
    (R_M/C_M/diferencia/ajuste/LIFO intactos).
  - Respuesta gana las líneas: `bancos` (=R_M), `transito_wava` (=Y), `caja_total` (=R_M+Y).
- **Compensación O1:** si el emit falla, `transito_wava` vuelve a su valor previo (capturado antes) junto con
  el resto de la reversa.
- `reabrir_mes`: revierte `transito_wava` a 0 (la declaración muere con el cierre). El "tránsito heredado" de
  M+1 se **deriva** de `MesControl(M).transito_wava` (compute-only, nunca copiado) → reapertura/re-cierre
  propagan limpio sin lógica adicional.

## 4. Remanente derivado y respuestas (P-4)
- `remanente(mes_actual)`: sea `mc_prev` = último mes CERRADO con `transito_wava > 0`:
  `remanente = max(0, mc_prev.transito_wava − Σ valor de txs (tipo INGRESO, rubro_id = «Tránsito Wava mes
  anterior», fecha > mc_prev.mes fin))`. **Rueda hacia adelante** (no expira en M+1 — un settlement tardío
  sigue contando) hasta agotarse; **clampeado en 0** (la sobre-llegada es recaudo normal del mes, no se
  clasifica al tránsito).
- Respuestas (additive, nada se rompe si Y=0):
  - `GET /meses`: por mes, `transito_heredado` (derivado, 0 si no hay) y `caja_inicial_total =
    saldo_inicial_caja + transito_heredado`.
  - `GET /meses/{mes}/control`: `caja_disponible_bancos` (= hoy `caja_disponible`), `transito_remanente`,
    `caja_disponible_total = caja_disponible_bancos + transito_remanente`.
  - Cierre (confirmar + dialog): las tres líneas del punto 3.
- **Aviso al cierre siguiente:** si al cerrar el mes N existe `remanente > 0` (del tránsito declarado en
  N−1): campo `aviso_transito` con texto *"declaraste $Y en tránsito y solo llegaron $W (remanente $Z)"* en
  la conciliación/respuesta de cierre. Informativo, no bloquea.
- **Caso `transito_heredado = 0` inocuo** (agosto-2026 pre-módulo y todo mes sin declaración): respuestas
  idénticas a hoy, sin aviso.

## 5. Clasificación de los depósitos (P-5)
- Vía manual (ya funciona): `PATCH /transacciones/{id}/clasificar` al rubro tránsito (whitelist).
- Vía regla C3 dedicada: **patrón real lo provee el CEO** de extractos reales (R5 — no se inventa). Si lo
  entrega durante la construcción: regla con **prioridad MENOR** que las genéricas ('Abono'/'Recibido de' →
  'Recaudo de cartera') para que gane; `origen=manual`. Si no lo entrega: los depósitos se clasifican a mano
  en agosto (el remanente solo cuenta lo clasificado al rubro).

## 6. Migración `20260803_wava_transito.py`
Idempotente, URI por env, DRY-RUN por defecto: (a) siembra el rubro (`$setOnInsert`, reporte de colisión);
(b) verifica que todos los `MesControl` leen con el campo nuevo (foto: estados, `transito_wava=0`);
(c) reporta. Se corre en PROD tras el merge.

## 7. Frontend
- `CerrarDialog` (CabinaMes): input **"Dinero en tránsito (Wava)"** (default 0, valida monto) + tres líneas
  (Consolidado bancos · En tránsito · Total). El Idempotency-Key se regenera por apertura de diálogo (patrón
  existente).
- `MesesPage`: línea "Tránsito Wava" cuando `transito_heredado > 0` (y total).
- `ControlPage`: la caja muestra bancos + remanente + total cuando `transito_remanente > 0`.
- Montos string (regla 1), "—" cuando 0/ausente.

## 8. Tests obligatorios (la trampa del CR + los del arquitecto)
1. **La trampa:** llegada del depósito NO infla el recaudo (`ingreso_real` inmóvil) NI cambia la caja total
   (banco sube, remanente baja, total igual).
2. **P-1:** exclusión por `rubro_id` en `ingreso_real` (tránsito + ajuste; Recaudo sigue contando).
3. **Hash:** misma key + otro `transito_wava` → 422; mismo payload → replay.
4. **O1:** fallo de emit → `transito_wava` revertido (+ resto de la reversa intacta). Reapertura →
   `transito_wava = 0` y el heredado desaparece.
5. **Remanente:** llegada parcial (Y=100, llegan 60 → 40); sobre-llegada (llegan 120 → remanente 0, exceso no
   cuenta); roll-forward (llegada en M+2 descuenta del mismo Y); aviso al siguiente cierre con remanente > 0.
6. **`transito_heredado = 0` inocuo:** respuestas idénticas a pre-módulo.
7. **Cierre completo con tránsito:** persiste en `MesControl`, metadata de `mes.cerrado` la lleva, respuesta
   con tres líneas; el mes siguiente deriva el heredado.
8. **Regla Wava** (si hay patrón): gana a 'Abono' genérico por prioridad.
9. **Candados existentes verdes sin tocarlos:** dorados cierre/conciliación, golden master, compuerta A14,
   guard es_sistema, replay/O1/idempotencia FIX-A.

## 9. Secuencia de ejecución (TDD, un PR)
1. Rama `feat/cr-wava` desde main. Orden: **dominio+semilla → P-1 (`ingreso_real`) → cierre
   (input/hash/persistencia/O1/reapertura) → remanente+respuestas → migración → frontend → tests completos**.
2. `pytest` local + `ruff check` + `ruff format --check`; candados real-mongo donde haya concurrencia; CI 7/7.
3. Gate directo al diff del repo (≥9). Merge → correr migración en PROD (DRY-RUN → visto → APPLY).
4. En paralelo/independiente: FIX-B (ya HECHO — clasificación de egresos de julio) — requisito para cerrar
   julio con el gasto real completo.
5. **Cierre de julio CON tránsito:** `transito_wava = 37.280.415` → agosto muestra Bancos 665.715.578 ·
   Tránsito 37.280.415 · Total 702.995.993. Enmienda de la NOTA en el mismo PR de docs.
6. Después: E1 (reanuda; su exclusión de rubros neutros por `rubro_id` ya contempla este rubro — ahora
   existente).

## 10. Pendiente del CEO (una sola cosa)
El **patrón real del depósito Wava** en el extracto bancario (cómo se lee "Wava" en Global66) para la regla
de clasificación automática. Sin él: clasificación manual en agosto (ya soportada).

---
*Kimi — arquitecto de COMPAS. Este I-PLAN reemplaza la secuencia "Wava después de E1" del roadmap v2
(reorden aprobado por el CEO 2026-08-02).*
