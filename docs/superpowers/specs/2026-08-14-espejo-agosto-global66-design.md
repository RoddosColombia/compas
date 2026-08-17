# Espejo agosto Global66 en PROD — Diseño

**Fecha:** 2026-08-14
**Rama:** `fix/agosto-espejo-global66`
**Tipo:** migración de datos reales (carga bancaria) → **gate crítico**: TDD + auditoría Kimi ≥ 9.0 + GO del CEO antes de correr contra PROD.

---

## 1. Problema (una oración)

La ejecución del presupuesto de agosto sale mal porque en PROD solo están cargados los movimientos de **agosto 1–4** (42 tx), mientras la fuente al día — la hoja **"Global66 ago-2026"** del libro `Flujo de pagos deudas.xlsx` — trae **agosto 1–12** (~225 movimientos) ya clasificados.

## 2. Objetivo

Dejar **PROD agosto = Excel "Global66 ago-2026"**: insertar los movimientos faltantes (ago 5–12, ~183) y alinear el rubro de todos al que dicta el Excel (columna *Detalle*), para que la ejecución del presupuesto de agosto sea fiel.

**Fuera de alcance:** otros meses; otros bancos (mar–jul y Bancolombia/BBVA no se tocan); reglas de clasificación (no se crean/editan).

## 3. Evidencia (verificada read-only contra PROD, 2026-08-13/14)

| | PROD (hoy) | Excel "Global66 ago-2026" |
|---|---|---|
| Cobertura | ago 1–4 | ago 1–12 |
| Movimientos | 42 (41 global66 + 1 ajuste manual) | ~225 con ID |
| Σ egresos | 59.835.163,78 | **150.673.115,59** (footer) |
| Σ ingresos | 37.181.794,69 | **99.424.130,75** (footer) |
| `meses_control` 2026-08 | existe, `en_ejecucion` | — |

- Los 42 entraron por el flujo de cargas estándar (2 `CargaBancaria`, dedup + reglas + auditoría).
- De los 42: 33 ya con rubro correcto, 1 cambio claro (Viajes corporativos $1.515.306, hoy "Por clasificar"), 3 en categorías de ingreso a resolver.

## 4. Fuente de verdad de la clasificación

Hoja **"Global66 ago-2026"** — columnas: `Tipo mov (A)`, `Fecha (B)`, `Débito (C)`, `Crédito (D)`, `Saldo (E)`, **`Detalle (H)`** (= categoría correcta), **`ID transacción (M)`** (= referencia nativa Global66 = `id_banco` en PROD). El footer (filas sin `Fecha`) son totales, **se excluyen**.

Se **snapshotea** esa hoja a un archivo del repo (`docs/modelo/Global66_ago2026_clasificado.xlsx`) para que migración y tests sean herméticos y reproducibles (precedente: `docs/modelo/Global66_COP_ene-jul2026.xlsx`).

### Mapeo categoría (Detalle) → rubro (PROD)

21 categorías mapean **directo por nombre** al rubro homónimo. 3 decisiones del CEO + 1 rubro nuevo:

| Categoría Excel | Rubro destino | Nota |
|---|---|---|
| `Operativo` (ingreso, Wava) | **Recaudo de cartera** (0110) | recaudo cuotas semanales/iniciales sin discriminar (CEO). Rubro de sistema. |
| `No operativo` (ingreso) | **Rendimientos bancarios** (NUEVO) | crear rubro ingreso, grupo `ingresos_operativos`, siguiente código libre. |
| `Ajuste` (ingreso) | **Reversas y devoluciones** | reembolsos/reversas. |
| `Garantía cupo` | **Garantía cupo** (4030) | match directo. |
| (otras 21) | rubro homónimo | Impuestos, Tecnología y software, Gastos bancarios, Transporte…, SOAT/Matrículas, Cafetería, Bonificaciones, Mercado y aseo, Préstamos, Deudas proveedores anteriores, Sueldos directivos/empleados, Rodante – Financiación a clientes, Gastos de representación, Por clasificar, Viajes corporativos, Otros gastos, Papelería, Mobiliario/planta/equipo, Combustible motos, Freelance. |

`tipo_flujo` por fila: **débito → egreso**, **crédito → ingreso**. El rubro destino debe coincidir en `tipo_flujo` (invariante verificado).

## 5. Arquitectura

Migración fechada e idempotente **`migrations/20260814_espejo_agosto_global66.py`**, con lógica pura extraída a helpers cubiertos por **TDD** (`backend/tests/migrations/`). Sigue el molde de `20260726_carga_inicial_global66.py` y **reusa** la maquinaria ya auditada por Kimi.

**Componentes (unidades con una responsabilidad):**

1. `leer_hoja_clasificada(path) -> list[MovAgosto]` — **puro/testeable**. Lee la hoja, excluye footer (fecha None), devuelve `{fecha, descripcion, monto, tipo, referencia, categoria}`. Reusa criterios del parser (`_a_decimal`, `_fecha_iso`).
2. `mapa_categoria_rubro(rubros) -> dict[str,ObjectId]` — **puro/testeable**. Construye el mapeo de §4 contra los rubros vivos; falla-fuerte si una categoría no resuelve o el `tipo_flujo` no coincide.
3. `construir_docs(movs, mapa, mc_id) -> list[Transaccion]` — **puro/testeable**. Reusa `_clave_ocurrencia` (ordinal por huella) + `movimiento_a_transaccion` → `id_banco`/ocurrencia **idénticos** al parser (dedup exacta; split Auteco `ref|1`/`ref|2`), con **rubro directo del Excel**.
4. `_run(uri, db, path, commit)` — orquesta contra Mongo:
   - **Seed idempotente:** rubro `Rendimientos bancarios` (si falta) + verificar `MesControl 2026-08` `en_ejecucion`.
   - **Insertar** solo los nuevos: pre-filtro de dedup dentro de `session` + `insert_many` + `with_transaction` (patrón exacto de `procesar_carga`, regla 8). Emite `transaccion.creada` por cada nuevo.
   - **Reclasificar** los existentes cuyo rubro ≠ Excel: `reclasificar_transaccion` para rubros clasificables; para destinos de **sistema** (Recaudo de cartera / Por clasificar) que ya estén correctos, no se toca; si estuvieran mal, set directo + `transaccion.clasificada` (helper mínimo, mismo audit que reclasificar).
   - **Cuadre** por día/tipo + verificación.

**Reuso explícito:** `_clave_ocurrencia`, `movimiento_a_transaccion`/`derivar_id_banco`, patrón `with_transaction`+pre-filtro de `procesar_carga`, `reclasificar_transaccion`, seeding de `MesControl` y URI-por-env-var de `20260726_carga_inicial_global66.py`.

## 6. Controles fail-loud (patrón E1)

- **Antes de escribir:** Σ del Excel (excluido footer) debe igualar el footer: **egresos 150.673.115,59 · ingresos 99.424.130,75**. Mismatch → `SystemExit`, no se escribe nada.
- **Cada movimiento** debe tener rubro resuelto y `tipo_flujo` coherente; categoría sin mapeo → aborta.
- **`--dry-run` por defecto**; solo `--commit` escribe. Dry-run imprime: N a insertar, N a reclasificar, sumas por tipo, y muestra de filas. El CEO revisa el dry-run y da GO antes del `--commit`.
- **Después del commit:** Σ agosto en PROD (egresos/ingresos) debe igualar el Excel; se imprime cuadre por día.
- **URI solo por env var** `MONGODB_URI_COMPAS` (nunca argv/historial).

## 7. Idempotencia

Re-correr no duplica (dedup por `(banco, id_banco)`) ni re-audita lo ya correcto (reclasificación se salta si el rubro ya coincide). El rubro `Rendimientos bancarios` y el seed se hacen con `find_one → insert si None`.

## 8. Edge cases

- **Footer** (filas sin fecha) excluido.
- **Split Auteco** (mismo `ID transacción`, 2 líneas) → ocurrencia 1/2 vía `_clave_ocurrencia`.
- **Filas sin ID nativo** → `derivar_id_banco` cae a huella determinista (igual que el parser); se listan en el dry-run para revisión.
- **agosto `en_ejecucion`** → reclasificar permitido (no es mes cerrado, regla 4).
- **Rubro de sistema como destino** (Recaudo/Por clasificar) → set en inserción (permitido) o helper directo con audit; nunca vía `reclasificar_transaccion` (que los bloquea).

## 9. Testing (TDD, primero el test)

- `leer_hoja_clasificada`: fixture con footer + split + fila sin ID → parsea bien, excluye footer, conserva categoría.
- `mapa_categoria_rubro`: mapea las 24 + falla-fuerte ante categoría desconocida / `tipo_flujo` incoherente.
- `construir_docs`: `id_banco` esperado (incluye ocurrencia del split); rubro = Excel; tipo por débito/crédito.
- Verificación de totales (helper puro) contra el footer.
- (Integración opcional con `mongomock`/staging: dedup salta existentes, inserta nuevos, reclasifica los desalineados.)

## 10. Gate y despliegue

1. TDD verde (pytest) + ruff.
2. **Dry-run contra PROD** (read-only) → revisión del CEO.
3. Paquete auditoría **Kimi ≥ 9.0** (SOLICITUD+EVIDENCIA+PDF) — flujo crítico.
4. `--commit` con GO del CEO. Verificación post-commit.
5. Actualizar `docs/COMPAS_Control_Desarrollo.xlsx` (tarea + Gate).
