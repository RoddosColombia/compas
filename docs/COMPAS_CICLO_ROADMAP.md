# Ciclo mensual — Roadmap de desarrollo (artefacto vivo)

> **Qué es:** el artefacto de control ÚNICO del avance de la fase «ciclo mensual» (cerrar
> el tejido entre la realidad de caja, el objetivo del mes y el recálculo de la
> proyección). Muestra la evolución pieza a pieza en el tiempo, no solo la foto de hoy.
> **Manda sobre cualquier conversación:** si algo lo contradice, gana este archivo.
>
> **Mecánica de actualización (regla del CEO 2026-08-10, misma que FABS):** se actualiza
> **tan pronto cierra cada pieza** (no al final de la fase). Cada cambio queda **fechado**
> en el Registro de cambios (§4). Responsable de revisarlo: Claude, en cada cierre.
>
> **Gobierno:** el contrato funcional es `docs/COMPAS_Ciclo_Mensual.md` (OK del CEO
> 2026-08-23) — si el código y el contrato discrepan, gana el contrato. Reglas
> innegociables: las de `CLAUDE.md`. **El motor no se toca en sus fórmulas:** cada cambio
> entra como parámetro cuyo default reproduce la serie certificada, y el valor de
> producto se configura como dato (golden master siempre verde).
>
> **Coordinación:** FABS corre en paralelo en otra terminal. Ningún merge sin OK del CEO.

## 1. Norte de la fase (una línea)

Que **cualquier cifra de la proyección se pueda rehacer a mano** con las columnas que
tiene al lado, partiendo del **efectivo real** del último cierre y del **objetivo** del
mes en curso — para decidir el presupuesto sobre proyecciones precisas, no sobre números
que no cuadran.

## 2. Piezas

Estado: ⬜ Pendiente · 🟡 En curso · ✅ Hecho · 🔒 Bloqueado

| # | Pieza | Qué entrega | Paso del contrato | Estado |
|---|---|---|---|---|
| **P1** | **Candado aritmético** | Test que recorre **todos** los meses del horizonte verificando las 4 fórmulas (`caja = caja−1 + flujo`, `flujo = neto + egresos`, `neto = inicial + semanales + ajuste`, `ajuste = mora + recup + default`). Se escribe PRIMERO: es el que demuestra que el resto funciona. | Candado | ✅ **Hecho** |
| **P2** | **Arranque heredado** | La proyección arranca del efectivo real del último mes cerrado (hoy usa `caja_inicial` tecleado). Override editable con rastro en `audit_log` (COMPAS no hace arqueos). | Paso 0 | ✅ **Hecho** |
| **P3** | **El primer mes acumula su flujo** | Quita la excepción del artefacto (`motor.py`: *"primer mes: caja fija"*). La caja de arranque pasa a ser un valor ANTERIOR al primer mes. | Candado | ✅ **Hecho** |
| **P4** | **Mes en curso = objetivo** | El mes en ejecución deja de anclar gasto real (muestra el presupuesto) y la carga semanal **deja de escribir la meta** — es dato del CEO. | Paso 1 | ✅ **Hecho** |
| **P5** | **Cronograma del mes completo** | La carga semanal conserva pagadas + parciales del mes en curso; corte de no-solape al cierre del mes anterior; cuota 0 nunca entra al recaudo. | Paso 1 | ✅ **Hecho** |
| **P6** | **Termómetro de desviación** | Bloque propio: colocaciones / ingreso / gasto reales contra el objetivo del mes. No toca la curva. | Paso 2 | ⬜ Pendiente |
| **P7** | **Promedio de gasto** | Promedio del gasto real de los **3 meses cerrados** más recientes; **SUGIERE** el supuesto hacia adelante y el CEO lo aprueba en Supuestos — nunca lo reemplaza en silencio (decisión CEO 2026-08-23). | Paso 4 | ⬜ Pendiente |

Piezas ya cerradas que pertenecen a este tejido (venían de SUP-5, sin mergear):

| # | Pieza | Estado |
|---|---|---|
| **P0a** | Mora / incumplimiento / provisión **solo sobre las cuotas semanales** (`mora_sobre_recaudo`, editable; default del motor = artefacto ⇒ golden verde) | ✅ Hecho, sin mergear |
| **P0b** | Un mes **en ejecución** conserva su mora (solo los CERRADOS la borran) — la columna «Ajuste mora/default» y el desglose contaban distinto | ✅ Hecho, sin mergear |
| **P0c** | Rótulos de la gráfica: cambian de ancla y crecen hacia donde hay espacio (ya no se encima con el eje) y nombran el mes | ✅ Hecho, sin mergear |

## 3. Gates y prerrequisitos

| Gate | Cuándo | Debe cumplirse |
|---|---|---|
| **Golden master** | en cada pieza que toque `motor.py` | serie certificada bit a bit; todo cambio entra como parámetro con default = artefacto |
| **Candado aritmético (P1)** | en cada pieza, de P1 en adelante | las 4 fórmulas cuadran en TODOS los meses del horizonte, en los 3 escenarios |
| **Verificación en PROD** | antes de cerrar P2, P4 y P5 | foto antes/después de la proyección con datos reales; agosto-2026 es el caso de prueba |
| **Kimi** | antes de mergear P2–P5 | crítico (toca cálculo de plata). Kimi está en SISMO: **gate-waiver GO CEO** + auditoría retroactiva, jamás simular que Kimi aprobó |
| **OK del CEO** | antes de cada merge | FABS corre en paralelo |

**Prerrequisitos / dependencias externas:**
- **Cronograma de SISMO:** ✅ verificado 2026-08-23 — trae pagadas, parciales y pendientes con saldo y mora (9.879 cuotas, 196 créditos). No requiere cambios en SISMO.
- **Cierre de agosto-2026:** P2 se prueba de verdad cuando exista un segundo cierre; hoy solo julio está cerrado (`saldo_inicial_caja` = 665.715.578).
- **Decisión del CEO para P7:** ventana del promedio (¿3 meses cerrados?) y si **reemplaza** el supuesto o solo lo **sugiere**.

## 4. Registro de cambios (fechado, append-only)

| Fecha | Pieza | Qué cerró / cambió | Evidencia |
|---|---|---|---|
| 2026-08-23 | — | **Diagnóstico de agosto-2026 en PROD (read-only).** Tres descuadres: ① la proyección arranca de `caja_inicial` tecleado (704.722.003) e ignora el cierre real de julio (665.715.578); ② `caja[ago]` = 704.722.003 no cuadra con su propio flujo (−134.885.415,48) — el arranque implícito sería 839.607.418,48, un número que no existe; ③ el ingreso de agosto (105.324.084,52) es menor que lo ya recaudado en el libro al día 12 (99.424.130,75). **El frontend es fiel:** las tres cifras de la pantalla salen tal cual del API. | diagnóstico read-only sobre PROD |
| 2026-08-23 | — | **Cronograma de SISMO verificado:** trae pagadas + parciales + pendientes. El truncamiento de agosto era del parser de COMPAS (descarta `pagada`), no de SISMO. Agosto mes completo = 137.504.210 de cuotas semanales (vs 34.992.968 que ve el motor) + 59.480.000 de desembolsos = **196.984.210**, dentro del rango 190–230 M que el CEO estimó. | `cronogramas (5).xlsx` (2026-08-19) |
| 2026-08-23 | P0a | **Mora solo sobre cuotas semanales.** `neto_por_mora(..., base_mora)` + `ParametrosMotor.mora_sobre_recaudo` (default False = artefacto) + `ParametrosProyeccion.mora_sobre_recaudo` (default True = regla del CEO) + publicado en `supuestos`. Mismo criterio que ya usaba el fondo de aval. TDD 8 tests; golden master verde. | `feat/sup5-variables-visibles` |
| 2026-08-23 | P0b | **Un mes en ejecución conserva su mora.** La borraba para todos los meses anclados; ahora solo cuando el ingreso sale del libro (CERRADO). Defecto propio de SUP-5, cazado con agosto en PROD. TDD 1 test nuevo. | idem |
| 2026-08-23 | P0c | **Rótulos de la gráfica sin encimarse.** `ubicar()` cambia el ancla del rótulo según el espacio disponible en vez de centrarlo a la fuerza a ML+32 (que metía ~110 px sobre la banda del eje) + halo `paintOrder` + el rótulo nombra el mes. 14/14 tests de gráficas verdes. | idem |
| 2026-08-23 | — | **Contrato del ciclo mensual escrito y aprobado por el CEO** (6 pasos, candado aritmético de 4 fórmulas, regla de no-solape, tabla de decisiones superadas: D-08/Regla A para el mes en curso y la automatización de la rampa de SUP-4). | `docs/COMPAS_Ciclo_Mensual.md` |
| 2026-08-23 | P1 | **CANDADO ARITMÉTICO cerrado.** 11 tests que recorren los 144 meses del horizonte en los 3 escenarios y por las 3 capas de la tubería (motor → E1 → D2), verificando las 4 fórmulas + dos invariantes extra (el bruto es exactamente inicial+semanales; los egresos son la suma de sus 9 conceptos). El defecto de P3 queda declarado con `xfail(strict=True)`: avisa el día que se arregle. | `tests/test_candado_aritmetico.py` |
| 2026-08-23 | P1 | **DEFECTO REAL CAZADO en la primera corrida:** al anclar un mes, E1 recalculaba `egresos` sin el **fondo de aval** (lo introdujo SUP-2 en el motor y `_fila_anclada` nunca lo aprendió) → todo mes anclado perdía ese egreso en silencio. En PROD, agosto-2026: **546.241,68** que desaparecían de la cuenta sin que el total luciera raro. Corregido conservándolo del motor, igual que Auteco. | `app/proyeccion/ejecucion/service.py` |
| 2026-08-23 | P2 | **ARRANQUE HEREDADO cerrado.** `_arranque_de_caja` lee `MesControl(mes_inicio).saldo_inicial_caja + tránsito heredado` — la MISMA definición que `caja_inicial_total` de la pantalla del ciclo (test que compara las dos pantallas). Sin pieza nueva: el ciclo ya derivaba el saldo del consolidado bancario (M-1/F-14) y ya permitía tecleárselo con motivo + evento `saldo_inicial.editado` (FIX-F). Se publica `arranque` en la respuesta (valor · origen `ciclo`/`semilla`/`override` · mes · saldo declarado · tránsito) y el pie del gráfico lo dice en palabras. 8 tests. | `tests/test_p2_arranque_heredado.py` |
| 2026-08-23 | P1·P2 | **Verificado en PROD (read-only), los 3 deltas de agosto-2026 explicados al peso:** caja de arranque 704.722.003 → **665.715.578** (cierre real de julio, P2); egresos −240.209.500 → **−240.755.741,68** (+546.241,68 del aval recuperado, P1); ingreso neto 105.324.084,52 → **112.333.009,52** (+7.008.925 = 63.717.500 × 11 %, la mora que ya no cae sobre la cuota inicial, P0a). Backend **1178 passed / 0 failed** (+1 xfail declarado), frontend **274 passed** + build. | diagnóstico read-only sobre PROD |
| 2026-08-23 | P7 | **Decisión del CEO:** promedio de los **3 meses cerrados** más recientes, y **SUGIERE** (el CEO aprueba en Supuestos), nunca reemplaza en silencio. P7 desbloqueada. | acta de esta sesión |
| 2026-08-23 | P5 | **CRONOGRAMA DEL MES COMPLETO cerrado.** `parsear_cronograma(..., mes_en_curso)`: el mes en curso cuenta sus cuotas por el monto PACTADO (pagadas, parciales o pendientes) porque es un mes completo de proyección; los meses futuros solo lo que aún puede llegar (un prepago no vuelve a entrar, una parcial cuenta su saldo); lo vencido de meses anteriores sigue reportándose aparte. **Regla de no-solape:** la serie es la cartera originada hasta el cierre del mes ANTERIOR (un crédito sin cuota 0 se asume preexistente). Con el cronograma real: agosto pasa de 34.992.968 a **126.001.530** de cartera existente. 9 tests. | `tests/test_p4_p5_mes_en_curso.py` |
| 2026-08-23 | P4 | **MES EN CURSO = OBJETIVO cerrado.** (a) `_egresos_anclados_del_mes`: un mes EN EJECUCIÓN usa su PRESUPUESTO — la Regla A / D-08 queda solo para meses cerrados; `_es_anclable` añade el fail-safe (sin presupuesto no se ancla, para no dejar el gasto en cero). (b) **La carga semanal deja de escribir la meta del mes**: la automatización de SUP-4 dejaba el remanente y con eso PISABA el dato del CEO (agosto estaba en 70 por decisión suya y la carga lo bajó a 35 — el origen del reclamo). La meta es dato del CEO; la carga devuelve `meta_del_mes`/`colocadas_del_mes` para el termómetro. 6 tests. | idem |
| 2026-08-23 | P4·P5 | **Simulado contra PROD (read-only, cero escrituras)** sustituyendo en memoria la serie y la meta. Agosto con meta 70: motos **70**, iniciales `127.435.000`, semanales `165.993.730` (126,0 M de cartera existente + 40,0 M de las nuevas), bruto `293.428.730`, **neto `275.169.420`**, flujo **+`33.299.982`**. Con meta 60 → neto `252.783.378`; con 47 (lo facturado hoy) → `222.471.426`. El candado ① sigue fallando en el primer mes: es P3. | `scratchpad/simular_p4p5.py` |
| 2026-08-23 | P3 | **EL PRIMER MES ACUMULA SU FLUJO — el candado queda sin excepciones.** `ParametrosMotor.primer_mes_acumula_flujo` (default False = artefacto ⇒ golden bit a bit; el servicio pasa True) y `reacumular(..., primer_mes_acumula)`, propagado a las TRES capas post-motor (E1 anclaje, D2 reconciliación, D1 impactos) — sin él, anclar el mes en curso cambiaba su flujo y dejaba su caja congelada. El arranque se DERIVA de la serie (`caja[0] − flujo[0]`), exacto, sin un segundo parámetro que pueda desincronizarse. El `xfail(strict=True)` de P1 desaparece: el candado corre limpio en los 144 meses. 9 tests. | `tests/test_p3_primer_mes_acumula.py` |
| 2026-08-23 | P3 | **Efecto colateral corregido en COCK-09** (`/proyeccion/comparar`): el rolling forecast arrancaba EN el mes ancla repitiendo su caja real — con el primer mes fijo el solape no se notaba, con el candado sería doble conteo del flujo de ese mes. Ahora el tramo real termina en el ancla y el forecast arranca el mes SIGUIENTE. | `service.comparar_vigente` |
| 2026-08-23 | P3 | **VERIFICADO en PROD (read-only): el tejido cierra en agosto-2026.** `inicial 109.230.000 + semanal 161.295.930 = bruto 270.525.930` · `+ ajuste −17.742.552,30 = neto 252.783.377,70` · `+ egresos −241.822.459,30 = flujo 10.960.918,40` · `arranque 665.715.578 + flujo = caja 676.676.496,40`. Las cuatro fórmulas, al peso, rehechas a mano. Backend **1203 passed / 0 failed / 0 xfail**. | simulación read-only |
| 2026-08-23 | P4 | **Meta de agosto aplicada en PROD: 60** (decisión CEO), por el servicio auditado con backup previo. Estaba en 35, valor que había escrito la automatización de SUP-4. | `scratchpad/prod_meta_agosto.py` |
| 2026-08-23 | — | **Tests de decisiones superadas, actualizados con su rastro** (no se acomodaron al código: cambió la regla de producto por decisión del CEO): `test_b3_regla_a_incluye_ejecutado_mayor_que_definido` → `test_b3_el_mes_en_ejecucion_usa_el_PRESUPUESTO`; los dos de la rampa-remanente de SUP-4; y dos fixtures que originaban créditos dentro del mes en curso (ahora los saca el no-solape). | `test_e1_anclaje.py`, `test_sup4_*.py` |

## 5. Estado de datos / decisiones abiertas del CEO

- **`caja_inicial` editable:** decisión CEO 2026-08-23 — se puede teclear si no coincide
  con la ejecución presupuestal. COMPAS **no** es un ERP contable: no hay arqueos ni
  conciliaciones extensas; las diferencias se mantienen pequeñas por buen seguimiento y
  se corrigen a mano con rastro.
- **Decisiones que este contrato supera:** **D-08 / Regla A** (el mes en curso anclaba
  gasto real) queda solo para meses cerrados; la **automatización de la rampa de SUP-4**
  (remanente hacia la meta) vuelve a ser la meta del mes.
- **P7 definida (CEO 2026-08-23):** promedio de los **3 meses cerrados** más recientes;
  **sugiere** el supuesto y el CEO lo aprueba en Supuestos. No reemplaza en silencio.

## 6. Refinamientos conocidos (para piezas siguientes)

- **`sensibilidad_vigente` y el tornado** heredan el arranque de la proyección: al cerrar
  P2 hay que verificar que el tornado se recalcule sobre el nuevo arranque (ya tiene
  `_fingerprint_capas` en la clave de caché, pero el arranque no está en la huella).
- **COCK-09 (`/proyeccion/comparar`)** ya re-ancla la caja al último mes cerrado — es
  exactamente el Paso 0, pero vive en otra pantalla. Al cerrar P2, revisar si esa ruta
  queda redundante o se convierte en la fuente única.
- **`piso_caja` / `capital_requerido` / valles / techo de gasto** cambian de valor con P2
  y P3. Ninguna es un cálculo nuevo, pero todas se muestran en pantalla: la foto
  antes/después en PROD debe incluirlas.
- **El mes de arranque del horizonte** hoy es el mes en curso. Con P3, la caja de arranque
  pasa a ser un valor previo al primer mes; hay que decidir si la tabla muestra una fila
  «arranque» o solo el dato en el encabezado.

---
*Creado 2026-08-23. Este archivo se actualiza al cerrar cada pieza (no al final de la fase).*
