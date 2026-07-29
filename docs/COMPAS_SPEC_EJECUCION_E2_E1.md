# COMPAS — Spec de ejecución E2 + E1
## Facturas e IVA · Anclaje de la proyección a la ejecución

**Versión 1.3 · 2026-07-28**
*v1.1 cerró nueve vacíos detectados en una relectura con criterio de auditoría: notas crédito, ejemplo aritmético de la liquidación, guarda contra anclar meses con datos incompletos, prueba de comprensión como gate, roles, límites operativos, zona horaria, plan de reversa y gobierno de arranque.*
*v1.2 incorporó la decisión D-16 (notas crédito fuera de E2).*
*v1.3 cierra las **tres condiciones y los tres hallazgos bajos de la auditoría externa de Kimi**: M-1 (bug de orden de detección de tipo en el extractor — **corregido y probado**), M-2 (rubros del mapeo E1 que no existen en la taxonomía certificada post-C1), M-3 (registro único de CR y conteo único del catálogo de eventos), más PII bajo Ley 1581, tope de lote con parseo fuera del event loop, y fixture A8 con títulos oficiales DIAN. **Ver Parte IX.***

**Autor de la especificación:** Claude Cowork (diseño de producto + QA)
**Ejecuta:** Claude Code (terminal, repo local)
**Decide y aprueba:** Andrés San Juan, CEO RODDOS S.A.S.
**Auditó la spec antes de ejecución:** Kimi — veredicto: 9.4/10 con tres condiciones, todas cerradas en esta versión. **E2 tiene aval para arrancar; E1 después, con gate entre ambos.**

Este documento está escrito para ser auditable por alguien que **no participó** en la conversación que lo originó. Todo dato tiene su fuente. Todo criterio de aceptación es objetivo.

---

## PROMPT DE ARRANQUE (pegar en Claude Code)

> Lee completo `C:\Users\AndresSanJuan\roddos-workspace\COMPAS\docs\COMPAS_SPEC_EJECUCION_E2_E1.md` antes de escribir una línea de código.
>
> Define dos sprints, **E2** (captura de facturas + módulo de IVA) y **E1** (anclaje de la proyección a la ejecución presupuestal), en ese orden. Contiene contexto de negocio, reglas inviolables, bitácora de decisiones del CEO, contratos de API verificados, criterios de aceptación y los hallazgos de una auditoría externa ya incorporados.
>
> Procede así:
> 1. **Gobierno de arranque** (Parte VIII §B): `git log origin/main --oneline -10` y repórtame qué hay mergeado **antes** de crear rama. No asumas que un sprint anterior está en `main`.
> 2. **Verificación previa** (Parte IV §0 y Parte V §0): confirma o refuta cada afirmación marcada `[VERIFICAR]`. **Si alguna resulta falsa, detente y repórtalo** — la spec se escribió sin acceso al repo privado. La auditoría ya encontró un caso real de esto (M-2, Parte IX).
> 3. Ejecuta **E2** completo, con TDD, un commit por pieza, y detente en el gate de revisión.
> 4. **No arranques E1** hasta que E2 esté mergeado y Andrés lo apruebe.
> 5. `motor.py` no se modifica en ningún caso. Cero diffs. Es criterio de aceptación, no preferencia.
> 6. Toda desviación respecto a este documento se registra en el PR con su justificación.
>
> `extraer_iva_dian.py`, en `docs/`, es un extractor de referencia **probado contra un documento real y ya corregido por el hallazgo M-1**. Pórtalo; no lo reescribas desde cero, y **no reordenes la detección de tipo de documento** (el porqué está comentado en el código).

---

# PARTE I — CONTEXTO (para quien no estuvo)

## 1. Qué es RODDOS y qué es COMPAS

**RODDOS S.A.S.** (NIT 901012622) es una fintech colombiana que vende motocicletas a crédito con cobro **semanal**. Compra las motos a **Auteco** con plazo diferido (hoy 150 días) y las vende con cuota inicial + cuotas semanales.

**COMPAS** es la aplicación interna de decisión presupuestal y de flujo de caja del CEO. Responde: *¿hasta cuándo aguanta la caja, y qué palanca la mueve?* Vive en `compas.roddos.com` (Vercel) con API en `compas-api-von1.onrender.com` (Render).

**Norte del producto** (`COMPAS_NORTE.md` del repo): el ciclo presupuestal mensual es el cimiento; la proyección debe reflejar la realidad ejecutada, no supuestos congelados.

## 2. Stack

- **Backend:** FastAPI + Beanie/MongoDB Atlas. `ruff` + `pytest`.
- **Frontend:** React + Vite + Tailwind 4 (tokens en `@theme` en `index.css`). `biome` + `vitest`. `decimal.js-light` para dinero.
- **CI:** GitHub Actions, 6 gates (incluye `gitleaks`).
- **Repo:** `RoddosColombia/compas`, **privado**.

## 3. Reglas inviolables

Un PR que las incumpla se rechaza.

| # | Regla | Por qué |
|---|---|---|
| **R0** | **`backend/app/proyeccion/motor.py` no se modifica. Cero diffs.** | Activo más valioso de RODDOS. Decisión textual del CEO: *"El motor es lo más valioso, no quiero tocar ni dañar el motor"*. Todo lo nuevo es **capa post-motor**. |
| **R1** | **Dinero en `Decimal` (backend) / string en la frontera / `decimal.js-light` (frontend). Nunca `float`, nunca `Number()`.** `Intl` solo para presentación. | Un centavo perdido en una app de decisión de caja destruye la confianza en todo lo demás. |
| **R2** | **Golden master verde** (`tests/test_golden_master.py` vs `golden/golden_simular.json`). | Candado de no-regresión: 176 meses × 16 campos. Verificado con 0 discrepancias. |
| **R3** | **Agregar eventos al audit log requiere CR explícito**, en el **registro único de CR** (Parte IX, M-3). | El log es inmutable y fail-closed. |
| **R4** | **Orden de capas post-motor obligatorio y testeado** (§4). | Cada peso tiene un único dueño → de ahí el test de no-doble-conteo. |
| **R5** | **No inventar datos.** Si un dato no está, la UI dice que no está. | Brief original del CEO: *"No inventes datos"*. |
| **R6** | **No cambiar lógica de negocio ni cálculos sin CR aprobado.** Un error de cálculo se **reporta**, no se corrige por cuenta propia. | Brief original del CEO. |
| **R7** | **Sistema de diseño F1 sin excepciones**: escala tipográfica por rol (`text-cifra-lg` 32px → `text-apoyo` 12.5px mínimo), tokens AA (`positivo #15803D`, `atencion #B45309`, `critico #B91C1C`, `ink-faint #64748B` mínimo para texto, `ink-decor #94A3B8` solo decorativo), **cian exclusivo para acción**, título de gráfico = conclusión. | Fase 1 del rediseño, ya desplegada. |
| **R8** | **Los rubros y el plan de cuentas se crean por la vía del ciclo (C1), no a mano ni por semilla ad-hoc.** | Hallazgo M-2: la spec referenciaba rubros inexistentes en la taxonomía certificada. La taxonomía tiene un dueño y un camino. |

## 4. Arquitectura de capas post-motor

```
motor.proyectar()                    ← R0: intocable
   → capa EJECUCIÓN      (E1)        ← realidad ejecutada; TODO menos Auteco
   → capa OBLIGACIONES   (D2)        ← Auteco por facturas y pagos + obligaciones recurrentes
   → capa IMPACTOS       (D1)        ← ajustes what-if del usuario
```

El corte es **por concepto**, no por ventana de meses: E1 gobierna todos los conceptos salvo Auteco; D2 gobierna Auteco. Sin solapamiento posible. *La auditoría confirmó que este corte evita efectivamente el doble conteo.*

Módulos existentes según D1/D2 — `[VERIFICAR]` rutas reales:

- `impactos.py` — ajustes declarativos + `reacumular` (mecánica de caja del motor)
- `valles.py` · `solvers.py` (bisección: techo, goal seek, punto de quiebre) · `kpis.py` (KPI espejados con candado de paridad)
- `reconciliacion.py` — ventana anti-doble-conteo de Auteco
- `_resultado_con` en `proyeccion/service.py` — punto único donde se aplican las capas, para que **toda** la app herede la serie corregida

## 5. Estado verificado del producto (2026-07-28)

Verificado con sesión autenticada en producción y contra el `openapi.json` público.

**Vivo:** rediseño F1 propagado, ciclo presupuestal completo (`sugerido → propuesto → definido → en_ejecucion → cerrado`), capa D1, capa D2 backend, sprint V1 (egreso visible; fondeo de Auteco aprobado por el CEO).

**Cifras de esa verificación** (fixtures y evidencia de auditoría):

| Hecho | Valor | Fuente |
|---|---|---|
| Golden master | 176 meses × 16 campos, **0 discrepancias** | corrida de `test_golden_master.py` por Cowork |
| Piso de caja proyectado | **−315.201.751,12** en 2027-05 | corrida del motor |
| Salto de costo por primer lote Auteco | 72 M (nov-26) → **528 M** (dic-26) | pantalla Proyecciones post-V1 |
| Gasto jul-26 · **proyección** | **193,5 M** | API proyección |
| Gasto jul-26 · **presupuesto aprobado** | **331,7 M** | módulo presupuesto |
| Gasto jul-26 · **ejecutado** (72 % del mes) | **237,6 M** | módulo control |
| Costo de alistamiento por moto | 692.005 = 227.800 matrícula + 83.000 GPS + 363.300 SOAT + 17.905 colchón | confirmado por el CEO |

**El problema que motiva E1, en una línea:** tres cifras distintas para el gasto del mismo mes, y la única que decide —la proyección— es la única que no mira la realidad.

## 6. Ejecución real por rubro, mar–jul 2026

Extraído de `Flujo de pagos deudas.xlsx`, hoja *Base real egresos*. Línea base de calidad de datos que E1 hereda. **Los nombres de esta tabla son los del archivo del CEO, no necesariamente los de la taxonomía certificada** (ver M-2).

| Rubro | Total | Movs |
|---|---|---|
| Producto (Auteco) | 183.999.998 | 2 (abr-26: 114.999.999 · jun-26: 68.999.999) |
| Bonificaciones | 96.328.624 | 39 |
| Préstamos | 77.476.738 | 30 |
| Otros gastos | 76.209.571 | 130 |
| SOAT/Matrículas | 55.837.942 | 23 |
| Seguros (Hunter) | 5.353.211 | 3 |
| Por clasificar | 5.055.000 | 4 |
| Impuestos | 3.188.509 | 180 (promedio 17,7 mil → parece GMF, no IVA) |
| Gastos financieros | 9.163 | 2 |
| Garantía cupo (Auteco) | — | 0 |
| Inventario Auteco (150 días) | — | 0 |

**Lecturas confirmadas por el CEO:**

- Los pagos a Auteco caen en **Producto**. El rubro *Inventario Auteco (150 días)* nunca recibe movimientos: no se mapea.
- Faltan **28.500.000** pagados a Auteco **desde la cuenta propia de Fabián**, fuera de bancos de RODDOS. Total real pagado: **184,0 M + 28,5 M = 212,5 M**, coherente con los ~212 M que reporta el CEO. *La auditoría confirmó el tratamiento: reduce deuda, no reduce caja.*
- **Garantía cupo está en cero porque el primer pago es en agosto de 2026.** No es problema de clasificación: es obligación futura.
- **Otros gastos y Por clasificar se dejan como están**; se reducen clasificando mejor con el tiempo.

---

# PARTE II — BITÁCORA DE DECISIONES DEL CEO

| # | Fecha | Decisión | Consecuencia técnica |
|---|---|---|---|
| D-01 | 2026-07-26 | *"El motor es lo más valioso, no quiero tocar ni dañar el motor"* | R0. Todo en capas post-motor. |
| D-02 | 2026-07-26 | Sin adelantos a Auteco mientras no los exijan | `adelanto = 0`; nota informativa en Supuestos. |
| D-03 | 2026-07-26 | No ajustar el costo de alistamiento, pero hacerlo **configurable** y renombrarlo | "Costos de alistamiento por moto vendida", componentes editables, Σ = 692.005. |
| D-04 | 2026-07-27 | Horizonte tope **180 meses**; el hito es el mes con menos caja y **puede haber varios** | Parámetros de valles y solvers. |
| D-05 | 2026-07-28 | El **mes en ejecución** usa lo **ejecutado**, actualizado **día a día** | E1, jerarquía de fuentes. |
| D-06 | 2026-07-28 | El **ingreso** es el **proyectado del motor**; a principio de mes el mes cerrado se actualiza con el **real logrado** | E1, columna de ingreso. |
| D-07 | 2026-07-28 | **Cada monto y cada cuenta son editables**; se pueden agregar o quitar | El mapeo rubro↔concepto es **dato, no código**. |
| D-08 | 2026-07-28 | **Aprobada la regla (A)** para el mes en curso: `ejecutado + max(0, definido − ejecutado)` | E1. Evita el sesgo optimista del día 1. Fórmula visible en pantalla. |
| D-09 | 2026-07-28 | El calendario de deuda con Auteco **está bien**; falta que **los pagos registrados resten deuda** | Auteco por libro auxiliar, no por rubro. |
| D-10 | 2026-07-28 | Registrar **cada factura de Auteco** para deuda, fecha de pago (+150 días) e IVA | Libro auxiliar (D2 §7) + libro de IVA (E2). |
| D-11 | 2026-07-28 | **El IVA a pagar se calcula cruzando** el IVA de las **recibidas** contra el de las **emitidas** | E2. Ya implementado: `GET /api/v1/facturas/liquidacion`. |
| D-12 | 2026-07-28 | *"No debería alimentar la proyección de caja aún; primero hagamos que calcule el IVA y después vemos cómo lo integramos al flujo"* | **E2 no toca la proyección.** Criterio: `GET /api/v1/proyeccion` idéntico bit a bit. |
| D-13 | 2026-07-28 | *"Cuando se cargue el documento, solo revise el campo llamado IVA y extraiga el valor para ir sumándolo en un total iniciando en mayo y finalizando en agosto, y así cada 4 meses"* | Ingesta por documento; el IVA **se lee, no se calcula**. Cuatrimestres may–ago / sep–dic / ene–abr. |
| D-14 | 2026-07-28 | *"Todos son pdfs"* — es la **Representación Gráfica de la DIAN**, y **todos son iguales** | Un solo parser. Sin OCR. Sin plantillas por proveedor. |
| D-15 | 2026-07-28 | Corregir la falta de captura **inmediatamente**: *"sin esto no nos permite saber nada"* | **E2 tiene prioridad sobre E1.** |
| D-16 | 2026-07-28 | *"No hemos emitido la primera nota crédito"* | Notas crédito **fuera de E2**, van a E2.1. Se conservan los tres mínimos del §2 bis como radar, sobre todo por las notas crédito **recibidas**, que el enunciado no cubre. |

---

# PARTE III — DESCRIPCIÓN DE LOS TRABAJOS

Qué se va a hacer y por qué, en prosa. Las Partes IV y V dicen cómo.

## Trabajo 1 — E2: encender el módulo de IVA (prioridad inmediata)

**El diagnóstico.** COMPAS ya tiene un módulo de IVA construido y funcionando en el backend: registra facturas y liquida por período cruzando IVA generado contra descontable, con arrastre de saldo a favor. Pero **no tiene puerta de entrada**: la pantalla de captura nunca se construyó, y la propia aplicación lo confiesa en su estado vacío. Un módulo terminado que no puede recibir un solo dato, y por lo tanto una liquidación que la empresa no puede ver.

**Lo que se va a hacer.** Construir la ingesta por documento. El operador carga el PDF que descarga de la DIAN; el sistema lo lee, extrae el valor del campo *IVA* —no lo recalcula—, deduce si es emitida o recibida comparando los NIT contra el de RODDOS, y la registra. La liquidación cuatrimestral queda visible con su desglose: generado, descontable, resultado del período, saldo a favor arrastrado, próximo pago a la DIAN.

**Por qué es factible con certeza y no una apuesta.** El PDF de la DIAN tiene capa de texto real (lo genera `wkhtmltopdf`, no es escaneado), su layout es idéntico para todos los documentos, y trae los campos necesarios en un bloque de totales rotulado. Se verificó extrayendo un documento real: IVA 1.452,94 sobre base 31.447,06 y total 32.900,00, con `base + impuestos = total` cuadrando exacto. El extractor de referencia se entrega junto con esta spec.

**Lo que explícitamente NO se hace.** No se integra el IVA al flujo de caja proyectado (D-12). El concepto `iva` de la proyección queda como está. Esa integración es decisión posterior, y tiene un matiz que hay que dimensionar antes: el IVA generado se causa con la factura, mientras que en un negocio de cuotas semanales el dinero entra durante meses, así que la salida de caja por IVA se adelanta frente al ingreso.

## Trabajo 2 — E1: anclar la proyección a la ejecución

**El diagnóstico.** Para julio de 2026 hay tres cifras de gasto: 193,5 M proyectados, 331,7 M aprobados y 237,6 M ejecutados. La que alimenta la decisión es la única que no mira la realidad.

**Lo que se va a hacer.** Una tercera capa post-motor que, para cada mes, arma la serie con la mejor fuente disponible: un mes cerrado vale lo ejecutado real; el mes en curso vale lo ejecutado más lo que queda del presupuesto aprobado (regla A, D-08); un mes futuro con presupuesto aprobado vale ese presupuesto; un mes futuro sin presupuesto sigue valiendo el motor. El ingreso lo manda el motor, salvo el mes cerrado, que se actualiza con el real (D-06). Cada mes que cierra empuja su realidad y los siguientes se recalculan desde ahí.

**Auteco queda fuera de esta capa.** Su calendario a 150 días está bien y no se toca (D-09); lo que falta es que los pagos hechos bajen la deuda, incluidos los 28,5 M pagados desde una cuenta que no es de RODDOS —que reducen deuda pero **no** son salida de caja de RODDOS, y contabilizarlos como egreso rompería la conciliación bancaria—. Por eso Auteco va por su libro auxiliar en la capa D2. El corte por concepto elimina el doble conteo de raíz.

**El mapeo rubro→concepto es dato editable, no código** (D-07): un rubro nuevo entra sin mapear y la interfaz lo señala; nunca se adivina su destino. **Y antes de sembrar el mapeo hay que verificar que los rubros existan** (M-2, R8).

## Trabajo 3 — Backlog acumulado

Hallazgos de QA y peticiones del CEO pendientes. Parte VI.

---

# PARTE IV — EJECUCIÓN DE E2

## §0. Verificación previa — obligatoria antes de codificar

Confirma o refuta leyendo el repo. **Reporta y detente si algo no coincide.**

1. `[VERIFICAR]` Existe el módulo de facturas con los cuatro endpoints de §1 y la liquidación implementa realmente *generado − descontable con arrastre de saldo a favor*.
2. `[VERIFICAR]` **Valores exactos que el servicio acepta** en `tipo`, `origen` y `tarifa_iva`. En el OpenAPI son **strings libres sin enum**: la verdad está en el código. Repórtame la lista.
3. `[VERIFICAR]` Cómo se calcula hoy el IVA de una factura (¿`base_gravable × tarifa_iva`?) y en qué unidad viene `tarifa_iva` (`19`, `0.19`, `"19%"`).
4. `[VERIFICAR]` Cómo el servicio **corta los períodos**: ¿ene–abr / may–ago / sep–dic, o conteo desde otra fecha ancla? **Riesgo silencioso más grave del sprint.**
5. `[VERIFICAR]` Valor de `PERIODICIDAD_IVA` y si es editable sin redeploy.
6. `[VERIFICAR]` Forma real de la respuesta de `GET /api/v1/facturas` y `/facturas/liquidacion` — el OpenAPI las declara sin schema (`{}`). Tipa el cliente contra la respuesta real.
7. `[VERIFICAR]` El NIT de RODDOS **901012622** está o debe quedar en configuración.
8. `[VERIFICAR]` **Cuántas facturas hay hoy en la colección.** La pantalla dice cero; si es cero, la migración no tiene riesgo de datos y el índice único se crea limpio. Si no es cero, repórtalo antes de migrar.
9. `[VERIFICAR]` **Roles y permisos** existentes: quién puede cargar, quién puede anular y **quién puede ver el detalle de una factura** (relevante por PII, ver §7).

## §1. Contrato actual de la API — verificado en el `openapi.json` de producción

| Método | Ruta | Nota |
|---|---|---|
| `POST` | `/api/v1/facturas` | crear (una a una) |
| `GET` | `/api/v1/facturas?activo=` | listar |
| `GET` | `/api/v1/facturas/liquidacion` | *"Liquidación por período (cuatrimestral o bimestral, según `PERIODICIDAD_IVA`) de las facturas activas: generado − descontable con arrastre de saldo a favor. Montos como string (regla 1)."* Sin parámetros. |
| `POST` | `/api/v1/facturas/{factura_id}/anular` | anular |

Body de `POST /api/v1/facturas` (`additionalProperties: false`):

| Campo | Tipo | Req. | Restricción |
|---|---|---|---|
| `tipo` | string | sí | **sin enum** |
| `origen` | string | sí | **sin enum** |
| `numero` | string | sí | 1–60 |
| `tercero_nombre` | string | sí | 1–200 |
| `tercero_nit` | string | sí | 1–30 |
| `fecha` | string | sí | sin formato declarado |
| `base_gravable` | string | sí | monto |
| `tarifa_iva` | string | sí | **sin enum** |
| `deducible` | boolean | no | **default `false`** |

**No existe** endpoint de carga de archivo para facturas. Los únicos dos `multipart/form-data` de la API son `POST /api/v1/cargas` (extractos bancarios) y `POST /api/v1/loantape/carga`.

**Existe un segundo registro de facturas, distinto y con el mismo nombre:** `POST /api/v1/obligaciones/{obligacion_id}/facturas`, body `{fecha_factura, valor, plazo_elegido_dias, nota}` — es el de plazos de Auteco (D2), colección separada.

## §2. Hechos verificados sobre el documento fuente

Documento analizado: `ALMACENES ÉXITO S.A mayo 28.pdf` (Carulla → RODDOS, 28/05/2026, 2 páginas).

- `/Title` = `Representación Gráfica Dian`; `/Creator` = `wkhtmltopdf 0.12.1.2`. **Capa de texto real, sin OCR.**
- **Sin XML embebido** (cero adjuntos). Se parsea el texto.
- Layout **idéntico** para todos los documentos (D-14) → **un solo parser**.

Extracción real obtenida:

```
tipo_documento  = FACTURA ELECTRÓNICA DE VENTA
cufe            = fabdb194877f049b698d92065704f28fec96e9c04dd0666444bebe43c56c01be12fcb1efd8968a5e837536db7422bfb3
numero          = UI90-16716
fecha           = 2026-05-28          → cuatrimestre may–ago
nit_emisor      = 890900608           nombre = ALMACENES ÉXITO S.A
nit_adquiriente = 901012622 (RODDOS)  → tipo = recibida
base_gravable   = 31447.06
iva             = 1452.94
inc / bolsas / otros = 0.00 / 0.00 / 0.00
total_impuesto  = 1452.94             total_factura = 32900.00
rete_fuente / rete_iva / rete_ica = 0.00 / 0.00 / 0.00
coherencia base + iva + inc + bolsas + otros == total_factura  →  True (exacto)
```

**Cuatro trampas encontradas al parsear** — comentadas en `extraer_iva_dian.py`:

1. **No usar regex por línea.** El layout de dos columnas de la DIAN intercala una barra lateral (`Documento generado el:`, `PDF Generado por:`) dentro de las filas de totales y **duplica las etiquetas** (`IVA IVA 1.452,94`). Un `^IVA\s+…$` lee bien unos campos y **falla en INC y en Total factura**. Se resuelve leyendo por **posición de palabra (x/y)** y tomando el último número de la fila.
2. **Tomar el campo `IVA`, no `Total impuesto`** — este suma IVA + INC + bolsas. En la muestra coinciden porque INC = 0, así que **el bug quedaría escondido**: hace falta un caso con INC > 0 o bolsas > 0.
3. **Formato COP**: miles con `.`, decimales con `,` → `Decimal`, nunca `float` (R1).
4. **Una factura puede mezclar tarifas** (en la muestra, dos líneas sin IVA y una al 19 %). El valor válido es el del **bloque de totales**, no el de las líneas.

## §2 bis. Documentos que NO son factura de venta

La DIAN emite otros documentos que **también llevan IVA y afectan la liquidación**:

| Documento | Efecto sobre el IVA | Riesgo si se ignora |
|---|---|---|
| **Nota crédito** (cód. 91) | **Resta** IVA | **IVA sobreestimado** si es emitida → pagar IVA que no se debe. **IVA descontable inflado** si es recibida → pagar menos del debido, riesgo con la DIAN |
| **Nota débito** (cód. 92) | **Suma** IVA | Subestimación |
| **Documento soporte** (compras a no obligados a facturar) | Puede generar descontable | Se pierde descontable |
| Nota de ajuste al documento soporte · documento equivalente | Ajustan | Se pierden |

**Decisión del CEO (D-16): RODDOS no ha emitido ninguna nota crédito** → no se procesan en E2, van a E2.1.

**Tres mínimos que SÍ entran en E2** — son el radar que avisa el día que aparezca la primera, sobre todo una **recibida**:

1. El parser **identifica el tipo de documento** por el encabezado del PDF y **rechaza con motivo explícito** lo que no sepa procesar. Nunca ingreso parcial.
2. El modelo lleva **`tipo_documento` y `signo`**, para que agregar notas crédito luego no exija migrar lo ya cargado.
3. El listado muestra un contador de **documentos rechazados por tipo no soportado**.

> ⚠ **HALLAZGO M-1 DE LA AUDITORÍA — no reordenar la detección de tipo.**
> El nombre oficial DIAN de la nota crédito es **"Nota Crédito de Factura Electrónica de Venta"**, que **contiene** la cadena `FACTURA ELECTRÓNICA DE VENTA`. La primera versión del extractor evaluaba el tipo soportado antes que los no soportados, así que **una nota crédito entraba como factura de venta** — exactamente lo que prometía impedir.
> **Corregido y probado:** los marcadores no soportados se evalúan **primero**, sobre el encabezado completo y con acentos normalizados; y el tipo soportado exige que el **título empiece** por él, no que la cadena aparezca en cualquier parte. Verificado contra los cuatro títulos oficiales (Parte IX, M-1).

## §3. Alcance de E2

**Backend**

1. Modelo de factura: agregar `cufe` (único), `tipo_documento`, `signo`, `iva_valor`, `inc`, `bolsas`, `otros_impuestos`, `total_factura`, `rete_fuente`, `rete_iva`, `rete_ica`, y referencia al archivo original.
2. **`iva_valor` manda sobre el cálculo.** Si viene, la liquidación usa ese valor y `base_gravable`/`tarifa_iva` quedan informativos (D-13: el IVA se lee, no se calcula). *Alternativa rechazada: derivar `base = iva / tarifa`, introduce redondeos en un dato fiscal.*
3. Endpoint de ingesta `POST /api/v1/facturas/cargar` (`multipart/form-data`, varios archivos): valida que sea representación DIAN, identifica tipo de documento, extrae, deduplica por CUFE, y devuelve por archivo `{estado: creada|duplicada|rechazada|requiere_confirmacion, datos_extraidos, motivo}`.
   **El parseo va fuera del event loop** (`anyio.to_thread` / `run_in_executor`): `pdfplumber` es CPU-bound y bloqueante; llamarlo dentro de un handler `async` congelaría el servidor en cada carga. **Con tope de archivos por lote.**
4. Índice único sobre `cufe`.
5. Endurecer `tipo`, `origen` y `tarifa_iva` con validación contra lista cerrada (endurecer, no cambiar lógica; si exige tocar el cálculo, **abre CR** por R6).
6. Guardar las retenciones aunque la liquidación no las use todavía: capturarlas ahora cuesta nada, reprocesar cientos de PDF después cuesta mucho.

**Frontend**

7. Pantalla de carga: arrastrar varios PDF, resultado por archivo (creadas / duplicadas / rechazadas / requieren confirmación), sin lenguaje técnico.
8. Pantalla de confirmación cuando la extracción no sea limpia: valor extraído junto al documento, aprobar o corregir. **Nada entra a la liquidación sin haber sido visto al menos una vez cuando hubo duda.**
9. Listado: filtros por tipo, tercero, período y estado; anular; contador de *recibidas sin marcar deducible* y de *rechazadas por tipo no soportado*.
10. `/iva`: liquidación con **la conclusión como título** (*"Este cuatrimestre pagarías $X a la DIAN"* / *"Quedas con saldo a favor de $X"*) y el desglose generado / descontable / arrastre debajo. Estados vacío, cargando y error explícitos (R7).
11. El estado vacío actual no lleva a ningún lado: debe ofrecer **"Cargar facturas"**.
12. Captura manual como excepción, con selector cerrado en `tipo` y `tarifa_iva`, y `deducible` como decisión explícita en recibidas.

**Fuera de alcance de E2:** integración con la proyección (D-12), notas crédito/débito y documentos soporte (D-16 → E2.1), retenciones dentro de la liquidación, vínculo automático factura Auteco ↔ obligación (recomendación §5).

## §4. Orden de ejecución — un commit por pieza, TDD

1. Portar `extraer_iva_dian.py` al backend + test con el PDF de muestra como fixture + **tests A8 con los cuatro títulos oficiales DIAN**.
2. Modelo y migración (`cufe` único, campos nuevos) — **idempotente**: se corre dos veces y la segunda no cambia nada.
3. Endpoint de ingesta + deduplicación + parseo en threadpool + tope de lote + tests.
4. `iva_valor` con precedencia en la liquidación + tests de período.
5. Endurecimiento de enums + tests.
6. Frontend: carga → confirmación → listado → liquidación.
7. Gate de revisión: reportar a Andrés y esperar aprobación antes de merge.

## §5. Recomendación abierta (decide Andrés, no Claude Code)

Los dos registros de facturas están separados, así que **una factura de Auteco habría que cargarla dos veces**: una para el IVA descontable, otra para la obligación con su vencimiento a 150 días. Con ingesta por documento hay una salida elegante: que un solo archivo cree **ambos registros vinculados**. No se implementa sin aprobación explícita.

## §6. Ejemplo aritmético de la liquidación — caso de prueba obligatorio

*Verificado a mano por la auditoría externa: cuadra exacto.*

**Cuatrimestre 2026-C2 (may–ago)**

| Documento | Tipo | Deducible | IVA |
|---|---|---|---|
| Carulla UI90-16716 (el PDF real) | recibida | sí | 1.452,94 |
| Auteco (lote) | recibida | sí | 19.000.000,00 |
| RODDOS → cliente | emitida | — | 8.000.000,00 |

- Generado = **8.000.000,00**
- Descontable = 1.452,94 + 19.000.000,00 = **19.001.452,94**
- Resultado = 8.000.000,00 − 19.001.452,94 = **−11.001.452,94**
- → **A pagar: 0. Saldo a favor que se arrastra: 11.001.452,94**

**Cuatrimestre 2026-C3 (sep–dic)**

| Documento | Tipo | Deducible | IVA |
|---|---|---|---|
| RODDOS → cliente | emitida | — | 15.000.000,00 |
| Proveedor X | recibida | sí | 2.000.000,00 |
| Proveedor Y (gasto no descontable) | recibida | **no** | 500.000,00 |

- Generado = **15.000.000,00**
- Descontable = **2.000.000,00** (los 500.000 de la no deducible **no entran**)
- Subtotal = 13.000.000,00
- Menos arrastre del C2 = 11.001.452,94
- → **A pagar: 1.998.547,06. Saldo a favor remanente: 0**

**Tres cosas que este ejemplo prueba y que ningún otro test cubre:** que el saldo a favor no se presenta como pago negativo; que el arrastre se aplica al período siguiente y se agota; y que `deducible = false` excluye del descontable sin excluir del registro.

## §7. Operación

| Tema | Definición |
|---|---|
| **Quién carga y quién anula** | El estado vacío actual dice *"financiero o admin"*. `[VERIFICAR]` los roles reales y que la UI los respete. Anular tiene efecto fiscal: queda en el audit log con autor (**R3: abre CR en el registro único si hay evento nuevo**). |
| **PII y Ley 1581** | Las facturas **emitidas** llevan datos de personas naturales (nombre, NIT/cédula, dirección, correo). Aplica la Ley 1581 de 2012: **rol de lectura restringido** para el detalle de factura y el archivo original, minimización en listados y exportables, y sin PII en logs ni en mensajes de error. `[VERIFICAR]` si ya existe un rol adecuado o hay que crearlo. |
| **Límites del lote** | Tope de archivos por carga y tamaño máximo por archivo, coherentes con el límite de 10 MB de los extractos bancarios. **Parseo en threadpool** (§3.3). Resultado parcial: si el archivo 7 de 20 falla, los otros 19 se procesan y se reporta cuál falló. |
| **Zona horaria** | `America/Bogota` para todo lo que dependa de "hoy" (mes en curso, día de carga, corte de período). Declararlo explícito evita que un servidor en UTC mueva una factura de cuatrimestre en las fechas de frontera. |
| **Archivo original** | Guardar referencia al PDF (o su hash) para poder auditar una cifra contra su documento. Sin esto, una discrepancia futura no se puede resolver. Con el control de acceso del punto de PII. |
| **Migración** | Idempotente y verificada: foto antes/después, segunda corrida sin cambios. Mismo patrón que la migración de componentes de alistamiento ya ejecutada en producción. |
| **Plan de reversa** | El índice único y los campos nuevos se retiran con un `$unset` sobre las facturas creadas y el borrado del índice; la colección estaba vacía antes de E2, así que la reversa es limpia. Escribir el comando exacto en el PR, **no ejecutarlo sin aprobación**. |

## §8. Criterios de aceptación de E2 (objetivos, auditables)

| # | Criterio | Cómo se comprueba |
|---|---|---|
| A1 | Caso de oro: el PDF de muestra produce IVA **1.452,94**, base **31.447,06**, total **32.900,00**, tipo **recibida**, cuatrimestre **may–ago** | test con fixture en repo |
| A2 | Cargar el mismo archivo dos veces no duplica | test de deduplicación por CUFE |
| A3 | Factura del 30-abr y del 1-may caen en cuatrimestres distintos | test de frontera |
| A4 | `tipo` deducido del NIT; documento donde RODDOS no es emisor ni adquiriente → **rechazado** | test |
| A5 | Con INC > 0 o bolsas > 0 se toma **solo** el IVA, no `Total impuesto` | test (**obligatorio**: sin él el bug se esconde) |
| A6 | Documento con `base + impuestos ≠ total` → **no se guarda**, pide revisión | test |
| A7 | PDF que no es representación DIAN → rechazado con mensaje claro | test |
| **A8** | **Los cuatro títulos OFICIALES DIAN se rechazan**, no versiones simplificadas: `"Nota Crédito de Factura Electrónica de Venta"`, `"Nota Débito de Factura Electrónica de Venta"`, `"Documento Soporte en Adquisiciones Efectuadas a No Obligados a Facturar"`, `"Nota de Ajuste al Documento Soporte"`. Y una factura de venta legítima **sí** se acepta (control anti-falso-positivo) | test parametrizado; fixtures en `TITULOS_A8` del extractor |
| A9 | Con descontable > generado la UI dice **"saldo a favor"**, nunca "pago negativo", y se ve el arrastre | test + revisión visual |
| A10 | El ejemplo del §6 reproduce exactamente **11.001.452,94** de arrastre y **1.998.547,06** a pagar, y la no deducible queda excluida del descontable | test end-to-end |
| A11 | Anular retira la factura de la liquidación y queda registrado con autor | test |
| A12 | Dinero como `Decimal`/string extremo a extremo; cero `float`, cero `Number()` sobre dinero | grep + revisión de diff |
| A13 | Migración idempotente: segunda corrida sin cambios | corrida doble |
| A14 | **`GET /api/v1/proyeccion` idéntico bit a bit antes y después** | foto pre/post, diff vacío |
| A15 | Las pantallas nuevas **pasan la prueba de comprensión de 10 segundos** con alguien que no participó en el diseño (`COMPAS_Guion_Prueba_Comprension.md`) | registro de la prueba |
| A16 | **El parseo no bloquea el event loop** y el tope de lote se respeta | test de carga concurrente o inspección del handler |
| A17 | **El detalle de factura y el archivo original solo son accesibles por el rol autorizado**; sin PII en logs | test de autorización + grep de logs |
| A18 | `motor.py` cero diffs · golden master verde · suites verdes · CI 6 gates verdes | CI |

---

# PARTE V — EJECUCIÓN DE E1

**No arrancar hasta que E2 esté mergeado y aprobado.**

## §0. Verificación previa

1. `[VERIFICAR]` `control/service.py` expone ejecutado **y** definido por grupo/rubro y por mes; `_ABIERTO = (EN_EJECUCION, CERRADO)`; `_egresos_por_rubro` filtra `tipo_flujo == EGRESO`.
2. `[VERIFICAR]` `MesControl` permite conocer el estado del ciclo por mes.
3. `[VERIFICAR]` Existe fuente del **ingreso real** por mes (transacciones de tipo INGRESO).
4. `[VERIFICAR]` `_resultado_con` en `proyeccion/service.py` es el punto único donde se aplican las capas.
5. `[VERIFICAR]` `reconciliacion.py` (D2) y su ventana de Auteco: confirmar que su alcance es **solo Auteco**, para que el corte por concepto de R4 funcione sin exclusiones de ventana.
6. **`[VERIFICAR]` — HALLAZGO M-2, BLOQUEANTE DE E1: existencia real de cada rubro del mapeo §2 en la taxonomía certificada post-C1.** La auditoría encontró que la spec referenciaba rubros que **no existen** en la semilla vigente:
   - los **cuatro rubros de ingreso** del concepto `neto` (Recaudo de cartera, Cuotas iniciales, RODANTE, Otros ingresos) **no están en la semilla**;
   - **Garantía cupo** y **Deudas impuestos** **fueron retirados en el re-seed** y solo sobreviven como rubros viejos activos pendientes de depuración.

   **Procedimiento:** listar la taxonomía vigente, cruzarla contra el mapeo §2, reportar los faltantes, y **crearlos por la vía del ciclo C1** (R8) **antes** de sembrar el mapeo. No sembrar mapeos contra rubros inexistentes y no crear rubros a mano.

## §1. Jerarquía de fuentes

| Estado del mes | Gasto y costo (**excepto Auteco**) | Ingreso |
|---|---|---|
| **Cerrado** | ejecutado real | real recaudado |
| **En ejecución** | `ejecutado + max(0, definido − ejecutado)` (regla A, D-08) | proyectado del motor |
| **Futuro con presupuesto aprobado** | el presupuesto aprobado | proyectado del motor |
| **Futuro sin presupuesto** | motor paramétrico (como hoy) | proyectado del motor |

Auteco va por D2 en todos los meses. Con `ejecutado > definido`, el mes vale el ejecutado: no se "des-gasta".

## §2. Mapeo rubro → concepto — tabla editable

**Sujeta a la verificación M-2 del §0.6: los nombres de abajo son la intención de negocio, no una afirmación de que existan en la taxonomía.**

| Concepto del motor | Rubros |
|---|---|
| `neto` (ingreso) | Recaudo de cartera · Cuotas iniciales · RODANTE · Otros ingresos — **verificar existencia; crear por C1 si faltan** |
| **Auteco** (`pago_inventario` + `fondeo`) | **no se mapea por rubro** — sale del libro auxiliar (D2). *Producto* se marca como *evidencia bancaria de Auteco*; *Inventario Auteco (150 días)* queda **sin mapear** |
| `costo_nueva` | SOAT/Matrículas · Seguros (Hunter) |
| `gps` | Seguros (Hunter) — comparte rubro; ver regla 2 |
| `gastos_fijos` | Operación + Nómina + Otros y varios + **Garantía cupo** y **Deudas impuestos** *(retirados en el re-seed: verificar y recrear por C1 si el negocio los requiere)* |
| `int_deuda` | Préstamos · Tarjetas · Proveedores anteriores |
| `iva` | Impuestos |

**Reglas de la tabla (D-07):**

1. Rubro nuevo → **sin mapear** por defecto, y la UI lo señala (*"3 rubros sin concepto asignado — no entran a la proyección"*). Nunca se adivina.
2. Un rubro no puede estar en dos conceptos, **salvo reparto explícito con porcentaje** (caso Hunter: GPS instalado vs. GPS mensual de cartera; ambos caen en el bucket *Costo* de V1, así que el total cuadra y solo el desglose interno queda aproximado).
3. Cambiar el mapeo cambia la serie → evento de auditoría (**R3: abre CR en el registro único**).

## §3. Implementación

- Lector de ejecución por mes y concepto, sobre `control.service`, usando la tabla del §2.
- Capa de anclaje aplicada **dentro de `_resultado_con`**, antes de D2 y D1 (R4), para que Inicio, Proyecciones, valles, techo, goal seek y escenarios hereden la serie anclada sin cambios propios.
- Exponer `meses_anclados: {mes: "cerrado" | "en_ejecucion" | "presupuesto"}`.
- Reutilizar `impactos.reacumular` para la mecánica de caja; no reimplementarla.
- **Pagos de Auteco desde cuentas de terceros** (los 28,5 M de Fabián): campo de origen de fondos; **reducen deuda, no reducen caja**. Contabilizarlos como egreso rompería la conciliación bancaria y hundiría la caja proyectada por una plata que nunca salió de RODDOS.

## §3 bis. Guarda contra anclar un mes con datos incompletos

**El riesgo:** anclar es sustituir una proyección por "la realidad". Si la realidad está a medio cargar, la app sustituye por una realidad falsa **y lo hace con toda la autoridad de un dato real**. El caso concreto: un mes cerrado cuyos movimientos no se cargaron completos se vería como un mes de gasto bajísimo y **mejoraría artificialmente toda la caja futura**. Es más peligroso que no anclar.

1. **No anclar en silencio un mes cuyo ejecutado sea anómalo.** Umbral configurable (sugerido: ejecutado < 50 % del definido en un mes ya cerrado) → la app **avisa** y pide confirmación explícita antes de usar ese mes como realidad.
2. **Mes cerrado sin presupuesto definido:** anclar al ejecutado, pero marcarlo como *sin presupuesto de referencia* para que no se lea como cumplimiento.
3. **Mes en ejecución sin presupuesto aprobado:** la regla (A) no aplica porque no hay `definido`. Usar el motor y marcarlo; nunca usar solo el ejecutado parcial.
4. **Indicador de completitud del mes en curso** visible junto a la cifra: *"gasto cargado hasta el 21 de julio"*.

## §4. UI

- Marca de origen por mes en la tabla (`real` · `en curso` · `presupuesto` · `proyección`), con el patrón visual de la ventana reconciliada de V1.
- Mes en curso: **fórmula (A) visible** (*"ejecutado $237,6 M + resto aprobado $94,1 M"*) y fila de comparación proyectado / ejecutado / desviación.
- Gráfico: tramo anclado sólido, proyectado punteado.
- Auteco: saldo de deuda, pagado a la fecha con desglose banco propio / tercero, próximo vencimiento con fecha exacta.
- **Efecto arrastre:** al cerrar un mes con desviación, una frase con cuánto cambió el saldo final del horizonte y el mes del valle.
- Aviso permanente mientras existan rubros sin mapear.

## §5. Criterios de aceptación de E1

| # | Criterio |
|---|---|
| B1 | **Sin ciclo corriendo** → la serie es **la base bit a bit**. Candado de no-regresión. |
| B2 | Mes cerrado → gasto/costo == ejecutado real al peso; la caja de los meses siguientes se re-acumula desde ahí |
| B3 | Mes en ejecución → regla (A); con `ejecutado > definido` vale el ejecutado |
| B4 | Registrar un pago de Auteco reduce el saldo y reduce o elimina el egreso futuro correspondiente, sin tocar otros conceptos |
| B5 | Pago desde tercero: **reduce deuda, no reduce caja**; la conciliación bancaria sigue cuadrando |
| B6 | Invariante de V1 intacto: `ingreso − (costo + gasto) == flujo` al peso en **toda** la serie, incluidos meses anclados |
| B7 | No-doble-conteo: con facturas, pagos y meses anclados simultáneos, ningún peso se cuenta dos veces |
| B8 | Suma de rubros mapeados a un concepto == valor del concepto en el mes anclado (test por concepto, fixture con la taxonomía **verificada**) |
| B9 | Rubro nuevo → sin mapear, **no entra** a la serie |
| B10 | **Mes cerrado con ejecutado anómalo** (< umbral) → **no se ancla sin confirmación** |
| B11 | Mes en ejecución **sin presupuesto aprobado** → no se usa el ejecutado parcial como si fuera el mes completo |
| **B12** | **Todo rubro del mapeo existe en la taxonomía vigente**; los que faltaban se crearon por la vía C1 y quedó registro de ello (M-2) |
| B13 | Las pantallas modificadas pasan la prueba de comprensión de 10 segundos |
| B14 | `motor.py` cero diffs · golden master verde · suites verdes |

## §6. Fuera de alcance de E1

Recalibrar los supuestos del motor a partir de los actuals. Integración del IVA al flujo (D-12). F4, D3, F6, F7.

---

# PARTE VI — BACKLOG PENDIENTE

## V1.1 — frontend: peticiones del CEO + hallazgos de QA de V1

1. **Tabla más grande con ingreso discriminado**: cuotas semanales (`recaudo_credito`) vs. cuota inicial (`cuotas_iniciales`).
2. **Costo discriminado**: activación de moto nueva (`costo_nueva`) vs. Auteco (`pago_inventario + fondeo`).
3. **Gama de rojos** para costo y gasto que haga juego con el verde de ingresos, **distinta del rojo `critico`** reservado para alertas (R7).
4. Etiquetas del eje X se superponen con el pie de la tarjeta.
5. **La línea de caja se lee como negativa** — aplicar la alternativa ya aprobada: dos paneles alineados sobre el mismo eje X.
6. *"Compromiso Auteco $0"* → mostrar el próximo compromiso (mes, monto, meses de distancia).
7. Falta la leyenda del gráfico.

## Arrastre de QA (abiertos)

8. **Goal seek sin UI** — el endpoint existe.
9. Estado vacío del selector de escenarios.
10. Razón visible del botón "Guardar" deshabilitado.
11. Selector de mes robusto.
12. *"Mes crítico — → —"*: lectura explícita cuando no hay dato.

## Roadmap restante (plan maestro)

**E2.1** (notas crédito, notas débito, documentos soporte) · D2 §7 (página de Obligaciones + registro de facturas + simulador de plazo + bloque de metas) · F4 fusionada · D3 · F6 · F7.

## Mejoras de clasificación recomendadas

13. Rubro dedicado **"IVA DIAN"**: hoy *Impuestos* tiene 180 movimientos por 3,2 M (promedio 17,7 mil, parecen GMF). Cuando llegue el pago del IVA se mezclará con ese ruido. **Crear por la vía C1** (R8).
14. Reducir *Otros gastos* (76,2 M / 130 movs) y *Por clasificar* (5,1 M) sembrando Reglas según `COMPAS_Protocolo_Diario_Cargas.md`. Decisión del CEO: por ahora se dejan como están.
15. **Depurar los rubros viejos activos** que el re-seed dejó atrás (M-2): decidir para cada uno si se recrea, se migra o se archiva.

## Protocolo y gobierno pendientes

16. **Protocolo de carga de facturas**, análogo al de movimientos bancarios: frecuencia de descarga de la DIAN, quién lo hace, qué se revisa, qué se hace con los rechazados. Sin protocolo, el módulo se enciende y se apaga en dos semanas. Se escribe cuando E2 esté en producción.
17. **Registro único de CR y conteo único del catálogo de eventos** (M-3). Ver Parte IX.

---

# PARTE VII — CHECKLIST DE AUDITORÍA

Cada punto es verificable de forma independiente: *cumple / no cumple / no aplica*, con evidencia.

## Integridad del motor

- [ ] `git diff` sobre `backend/app/proyeccion/motor.py` en todo el rango de commits de E2 y E1: **vacío**.
- [ ] `test_golden_master.py` verde contra `golden/golden_simular.json` **sin regenerar el golden**. Si fue regenerado, es hallazgo grave.
- [ ] Ninguna capa nueva llama a funciones privadas del motor ni duplica su lógica de acumulación de caja (debe reutilizar `impactos.reacumular`).

## Precisión monetaria (R1)

- [ ] Cero `float(` sobre valores monetarios en backend; cero `Number(`, `parseFloat(` o aritmética nativa sobre dinero en frontend.
- [ ] Todo monto cruza la frontera HTTP como **string**.
- [ ] El parser convierte el formato COP (`1.452,94`) con `Decimal`, no con `float`.
- [ ] `quantize` a centavo con `ROUND_HALF_EVEN` donde haya redondeo.

## E2 — extracción y liquidación

- [ ] Test con el PDF real como fixture y los valores exactos de A1.
- [ ] **Existe el test A5** (INC > 0 o bolsas > 0). Su ausencia es hallazgo: sin él, confundir `IVA` con `Total impuesto` pasa desapercibido.
- [ ] **Existe el test A8 con los cuatro títulos OFICIALES DIAN**, no simplificados, más el control de que una factura de venta legítima sí se acepta. **Si el orden de detección de tipo se invirtió respecto al extractor entregado, es hallazgo grave** (M-1): una nota crédito entraría como factura.
- [ ] **Existe el test A10** con el ejemplo aritmético del §6: arrastre 11.001.452,94 y pago 1.998.547,06 exactos.
- [ ] Test de frontera de período (30-abr / 1-may); cortes ene–abr / may–ago / sep–dic.
- [ ] Índice único sobre `cufe` presente **en la base**, no solo validado en código.
- [ ] Documento con `base + impuestos ≠ total` **no se persiste**.
- [ ] PDF que no sea representación DIAN se rechaza antes de parsear.
- [ ] `tipo` se deduce del NIT, no de entrada libre; documento ajeno rechazado.
- [ ] `deducible` exige decisión explícita en recibidas; no queda en `false` por omisión silenciosa.
- [ ] Saldo a favor: la UI **nunca** presenta un pago negativo.
- [ ] Se guarda referencia (o hash) del PDF original.
- [ ] Migración idempotente y con foto antes/después.
- [ ] **Parseo fuera del event loop** y tope de archivos por lote aplicado.
- [ ] **Detalle de factura y archivo original restringidos por rol**; sin PII en logs, listados minimizados (Ley 1581).

## E2 — no contaminación de la proyección (D-12)

- [ ] Foto de `GET /api/v1/proyeccion` antes y después de E2: **diff vacío**.
- [ ] Ningún cambio en `proyeccion/` dentro de los commits de E2.

## E1 — capas, doble conteo, taxonomía y datos incompletos

- [ ] Orden de aplicación efectivo EJECUCIÓN → OBLIGACIONES → IMPACTOS, verificable leyendo `_resultado_con`.
- [ ] Existe test B1 (sin ciclo corriendo, serie == base bit a bit).
- [ ] Existe test B7 de no-doble-conteo con facturas, pagos y meses anclados simultáneos.
- [ ] Existe test B6 del invariante `ingreso − (costo + gasto) == flujo` sobre **toda** la serie.
- [ ] **Existe test B10**: un mes cerrado con ejecutado anómalamente bajo **no se ancla sin confirmación**. Sin esta guarda, un mes mal cargado mejora artificialmente toda la caja futura — el riesgo más serio de E1.
- [ ] **B12: todo rubro del mapeo existe en la taxonomía vigente**, y los faltantes se crearon por la vía C1 con registro (M-2). Sembrar el mapeo contra rubros inexistentes es hallazgo grave.
- [ ] La capa E1 **no** toca Auteco; la capa D2 **solo** toca Auteco.
- [ ] Pagos de terceros: reducen deuda y **no** aparecen como egreso de caja.
- [ ] El mes en curso muestra su grado de completitud (*"cargado hasta el día N"*).

## Trazabilidad y gobierno

- [ ] Cada decisión D-01…D-16 que afecte código tiene implementación identificable, o justificación escrita de por qué no.
- [ ] Toda desviación respecto a esta spec está registrada en el PR.
- [ ] **Registro único de CR** con numeración única, sin dos series paralelas ni identificadores repetidos con significados distintos (M-3).
- [ ] **Un solo conteo del catálogo de eventos de auditoría**, reconciliado.
- [ ] Anular una factura queda registrado con autor.
- [ ] Roles: quién carga, quién anula y quién lee el detalle está definido y aplicado.
- [ ] Ningún secreto en el diff (`gitleaks` verde). Los 6 gates de CI verdes.
- [ ] Zona horaria `America/Bogota` explícita en todo cálculo que dependa de "hoy".
- [ ] Existe plan de reversa escrito para E2 (no ejecutado).

## Honestidad de la interfaz (R5)

- [ ] Ninguna pantalla presenta como cierto un dato que no tiene: los estados vacíos dicen qué falta y ofrecen la acción para resolverlo.
- [ ] El mes en curso muestra la fórmula con la que se armó, no solo el resultado.
- [ ] Los rubros sin mapear se avisan mientras existan.
- [ ] Las pantallas nuevas o modificadas **pasaron la prueba de comprensión de 10 segundos** con alguien ajeno al diseño, y el resultado quedó registrado.

---

# PARTE VIII — DECISIONES PENDIENTES Y GOBIERNO DE ARRANQUE

## §A. Decisiones que requieren a Andrés

1. ~~Notas crédito, notas débito y documentos soporte.~~ **RESUELTA — D-16: *"No hemos emitido la primera nota crédito"*** → no se procesan en E2, van a E2.1. Los tres mínimos del §2 bis siguen siendo obligatorios en E2.
   **Matiz vigente:** la decisión cubre las notas **emitidas** por RODDOS. Una nota crédito **recibida** de un proveedor también existe y **baja el IVA descontable**; ignorarla haría pagar **menos** IVA del debido — riesgo hacia la DIAN, dirección opuesta. Por eso el rechazo con contador visible no es opcional: es el radar.
2. **Alcance del histórico.** ¿Se carga solo el cuatrimestre en curso (may–ago 2026) o todo lo que exista del año? Determina el volumen de trabajo humano y si hace falta priorizar un importador masivo.
3. **Vínculo factura Auteco ↔ obligación (§5).** ¿Un solo archivo crea los dos registros, o se aceptan dos cargas separadas por ahora?
4. **Criterio de `deducible`.** Quién decide y con qué regla si el IVA de una compra es descontable. Es criterio del contador; el software solo necesita saber quién lo marca y cuándo.
5. **Rubros retirados en el re-seed** (M-2): ¿*Garantía cupo* y *Deudas impuestos* se recrean por C1, o el negocio los trata de otro modo? Sin esta decisión el mapeo de `gastos_fijos` queda incompleto.

## §B. Gobierno de arranque — lección ya aprendida en este proyecto

Antes de crear rama, Claude Code debe correr `git log origin/main --oneline -10` y **reportar qué está mergeado**. En este proyecto ya ocurrió que un sprint se especificó dando por mergeado otro que no lo estaba, y Claude Code correctamente se negó a ramificar. La regla es: **el estado de `main` se verifica, no se asume** — ni por Cowork al escribir la spec, ni por Claude Code al ejecutarla.

## §C. Advertencia metodológica

Esta especificación se escribió **sin acceso de lectura al repositorio** (privado desde 2026-07-26). Todo lo marcado `[VERIFICAR]` proviene del `openapi.json` público de producción, de la aplicación desplegada vista con sesión autenticada, de archivos aportados por el CEO, o de lecturas del repo anteriores a que se hiciera privado. **La verificación previa de las Partes IV §0 y V §0 no es opcional.** Si una afirmación resulta falsa, el hallazgo vale más que la spec.

**Esta advertencia ya se materializó:** el hallazgo M-2 de la auditoría demostró que el mapeo de E1 referenciaba rubros inexistentes en la taxonomía vigente. Es la prueba de que el §0 de cada parte es el paso más importante del documento, no un trámite.

---

# PARTE IX — AUDITORÍA EXTERNA Y SU CIERRE

Auditoría de la especificación **antes** de ejecución, 2026-07-28. Veredicto: extractor 8,5/10 → 9,3 con una línea; spec 8,8/10 → 9,4 con tres condiciones. **Aval para arrancar E2 con las tres condiciones cerradas.**

## Confirmaciones del auditor (evidencia independiente)

- La aritmética del §6 **cuadra exacta**: arrastre 11.001.452,94 y pago 1.998.547,06.
- Las afirmaciones sobre `control/service`, `MesControl`, fuentes de ingreso y convenciones son **exactas** contra su evidencia certificada.
- El tratamiento de los 28,5 M de tercero (**reduce deuda, no caja**) es **correcto por la razón correcta**.
- El §3 bis (guarda contra anclar meses incompletos) es **el diseño de riesgo correcto**.
- El corte por concepto entre E1 y D2 **evita efectivamente el doble conteo**.

## Condición M-1 — bug real en el extractor · **CERRADA**

**Hallazgo:** el orden de detección de tipo **aceptaba** las notas crédito oficiales. El nombre DIAN de la NC (cód. 91) es *"Nota Crédito de Factura Electrónica de Venta"*, que **contiene** `FACTURA ELECTRÓNICA DE VENTA`; al evaluarse primero el tipo soportado, una NC entraba como factura. Una NC **recibida** inflaría el descontable → **RODDOS pagaría menos IVA del debido, riesgo directo con la DIAN**. El docstring prometía lo contrario y el código lo derrotaba.

**Cierre:**
1. Los marcadores **no soportados se evalúan primero**, sobre el encabezado completo (6 primeras líneas) y con **acentos normalizados** (`NOTA CREDITO`/`NOTA CRÉDITO` indistinto).
2. El tipo soportado exige que el **título empiece** por él, no que la cadena aparezca en cualquier parte.
3. Marcadores cubiertos: `NOTA CREDITO`, `NOTA DEBITO`, `NOTA DE AJUSTE`, `DOCUMENTO SOPORTE`, `DOCUMENTO EQUIVALENTE`.
4. Los **títulos oficiales** quedan como constante `TITULOS_A8` en el extractor, para que el fixture no use versiones simplificadas.
5. **Probado:** los cuatro títulos oficiales se rechazan con motivo; la factura de venta legítima se acepta; el PDF real sigue dando IVA 1.452,94, base 31.447,06, total 32.900,00, `coherente=True`.
6. El bloque de código lleva un comentario que explica **por qué el orden importa**, para que nadie lo "limpie" en un refactor.

→ Criterio de aceptación **A8** reescrito con los títulos oficiales y el control anti-falso-positivo.

## Condición M-2 — rubros inexistentes en la taxonomía certificada · **CERRADA**

**Hallazgo:** el mapeo de E1 §2 referenciaba rubros que no existen en la taxonomía vigente post-C1: los cuatro rubros de ingreso del concepto `neto` **no están en la semilla**, y *Garantía cupo* y *Deudas impuestos* **fueron retirados en el re-seed** (sobreviven solo como rubros viejos activos pendientes de depuración). Yo tomé los nombres del archivo Excel del CEO y los presenté como si fueran la taxonomía de la aplicación.

**Cierre:**
1. Nueva regla **R8**: los rubros se crean **por la vía del ciclo C1**, no a mano ni por semilla ad-hoc.
2. Nuevo **`[VERIFICAR]` bloqueante en E1 §0.6**: listar la taxonomía vigente, cruzarla contra el mapeo, reportar faltantes y crearlos por C1 **antes** de sembrar el mapeo.
3. El §2 declara explícitamente que sus nombres son **intención de negocio, no afirmación de existencia**, y la tabla del §6 de la Parte I aclara que sus nombres son los del archivo del CEO.
4. Nuevo criterio **B12** y su ítem en el checklist.
5. Nueva decisión pendiente **VIII §A.5**: qué hacer con los dos rubros retirados.
6. Backlog **§15**: depurar los rubros viejos activos que el re-seed dejó atrás.

## Condición M-3 — gobierno de CR y del catálogo de eventos · **CERRADA en la spec, pendiente de ejecución**

**Hallazgo:** hay **dos series de CR** y **dos conteos del catálogo** de eventos de auditoría en circulación (una pista: CR-S2..S6 con 37 eventos; esta spec: CR-D1/D2 con 58), y un identificador **CR-002 duplicado con significados distintos**.

**Cierre:**
1. **R3 actualizada**: todo CR va al **registro único**, con numeración única.
2. Retiré de esta spec la numeración local `CR-002`: el cambio de costos de alistamiento se nombra por su contenido, y su identificador definitivo lo asigna el registro único.
3. Nuevo ítem de checklist: registro único sin series paralelas ni identificadores repetidos, y **un solo conteo del catálogo, reconciliado**.
4. Backlog **§17**: crear el registro único y reconciliar los dos conteos. **Debe hacerse antes de que E2 abra su primer CR**, para no agregar una tercera serie.

## Hallazgos bajos · **incorporados**

| Hallazgo | Dónde quedó |
|---|---|
| **PII en facturas emitidas a personas naturales** (Ley 1581): roles de lectura, minimización, sin PII en logs | §7 tabla de Operación · `[VERIFICAR]` IV §0.9 · criterio **A17** · checklist |
| **Tope de archivos por lote y parseo fuera del event loop** (`pdfplumber` es bloqueante; congelaría FastAPI) | §3.3 · §7 · criterio **A16** · nota en el docstring de `extraer()` |
| **Fixture A8 con el título oficial**, no simplificado | criterio **A8** · constante `TITULOS_A8` en el extractor |

---

## Anexo A — Archivos que acompañan esta spec

| Archivo | Contenido |
|---|---|
| `extraer_iva_dian.py` | Extractor de referencia probado contra el PDF real, **con el fix de M-1 y los títulos oficiales de A8** |
| `COMPAS_Sprint_E2_Captura_de_Facturas_IVA.md` | Razonamiento completo de E2 |
| `COMPAS_Sprint_E1_Anclaje_a_la_Ejecucion.md` | Razonamiento completo de E1 |
| `COMPAS_Protocolo_Diario_Cargas.md` | Protocolo diario de carga de movimientos (10 min/mañana) |
| `COMPAS_Guion_Prueba_Comprension.md` | Prueba de comprensión de 10 segundos — gate de A15 y B13 |
| `COMPAS_PLAN_MAESTRO.md` | Hoja de ruta completa |

## Anexo B — Qué NO cubre esta spec, dicho explícitamente

- **No define la integración del IVA con el flujo de caja.** Decisión pendiente (D-12), con el matiz de causación documentado.
- **No procesa notas crédito, notas débito ni documentos soporte.** D-16 → E2.1. Solo los rechaza con motivo y los cuenta.
- **No define el tratamiento de retenciones dentro de la liquidación.** Se capturan; su uso fiscal lo define el contador.
- **No recalibra los supuestos del motor** contra los datos reales. Requiere más meses cerrados; sería un sprint propio.
- **No incluye el protocolo operativo de carga de facturas** (Parte VI §16): se escribe con el módulo en producción.
- **No crea el registro único de CR** (M-3, Parte VI §17): es tarea de gobierno previa al primer CR de E2.
- **No sustituye el criterio del contador** en materia de causación, tarifas, deducibilidad ni retenciones.
