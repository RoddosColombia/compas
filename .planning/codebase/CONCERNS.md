# Codebase Concerns

**Analysis Date:** 2026-07-22

> Foco: gaps y riesgos del **producto vs el norte** (`docs/COMPAS_NORTE.md`,
> `.planning/PROJECT.md`). COMPAS es un sistema **PREDICTIVO de presupuesto y caja**,
> NO contable. El ciclo presupuestal (sugerido→acotar→aprobar→cierre) es el CIMIENTO
> ya construido; los concerns de abajo son lo que separa el cimiento del **valor**.
> Cada gap fue verificado contra el código real (no contra los .docx).

---

## Gaps de capacidad (producto vs norte)

Cada uno mapea a una capacidad C1–C8 de `.planning/PROJECT.md §3`.

### C1 — Categorías administrables (CRUD de rubros) — SEVERIDAD ALTA

- **Estado real:** Solo existe la **semilla**. No hay endpoint de gestión de rubros.
- **Evidencia:**
  - `backend/app/domain/rubro.py` define el `Document` + `SEMILLA_RUBROS` (33 rubros
    reales del Excel; 3 de sistema). Pero **no hay `rubro/router.py`**.
  - `backend/app/api/v1/__init__.py` registra `auth, cargas, ciclo, cierre, control,
    presupuesto, transacciones` — **no incluye ningún router de rubros**.
  - `backend/app/domain/seed.py::seed_rubros()` solo hace `$setOnInsert` (upsert
    idempotente de la semilla); no expone crear/editar/desactivar.
- **Impacto:** El CEO no puede crear/editar/desactivar categorías desde la app
  (capacidad C1 del norte, señalada como "corazón operativo"). Cualquier ajuste del
  catálogo exige tocar `rubro.py` + redeploy. La bandera `activo` existe en el modelo
  pero nada la muta.
- **Fix approach:** Nuevo módulo `backend/app/rubros/` (router+service) con
  `POST/PATCH/DELETE(soft) /api/v1/rubros`, RBAC (`ciclo:config` o similar de §2.4),
  respetando `es_sistema` inmutable (los 3 de sistema no se editan/desactivan) y el
  índice único `(grupo, nombre)`. Evento de auditoría: revisar el catálogo cerrado de
  31 (regla 11) — probablemente requiere CR para eventos `rubro.*`.

### C3 — Auto-clasificación de movimientos al cargar — SEVERIDAD ALTA

- **Estado real:** **No existe.** Todo movimiento cargado cae en 'Por clasificar'.
  No hay `ReglaClasificacion` implementada (grep de `ReglaClasificacion|clasificacion|
  regla_clasif` en `backend/` → 0 resultados).
- **Evidencia:**
  - `backend/app/cargas/service.py:126` resuelve un único rubro fijo:
    `rubro = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)` y lo pasa a
    **todas** las transacciones (líneas 173–181, `rubro_id=rubro.id`).
  - `backend/app/cargas/mapper.py:30` — el docstring lo dice literal: "Construye una
    Transaccion **'Por clasificar'**".
  - **No hay endpoint de reclasificación** para mover una transacción de 'Por
    clasificar' a su rubro real: `backend/app/transacciones/service.py` solo expone
    `crear_transaccion_manual` (que además default-ea a 'Por clasificar' si no llega
    `rubro_id`); no hay PATCH en `transacciones/router.py`.
- **Impacto:** El presupuesto por categoría (C5, Vista Control) queda vacío de datos
  reales: todo el egreso bancario aterriza en un solo cubo. Sin clasificación no hay
  ejecución por rubro, y sin ejecución por rubro el **motor del sugerido** (§1.4.1) no
  tiene insumo real y la **capa predictiva (C7)** no puede proyectar por categoría.
  Es el bloqueador funcional más caro después de C7.
- **Fix approach:** (1) entidad `ReglaClasificacion` administrable (patrón regex/
  contains sobre `descripcion`, prioridad, rubro destino); (2) aplicar reglas en
  `procesar_carga` al construir cada `Transaccion` (fallback 'Por clasificar' si
  ninguna matchea); (3) endpoint de reclasificación manual (PATCH transacción con
  step de auditoría). Semilla de reglas desde el mapeo categoría→rubro de
  `Base real egresos` (ver `docs/COMPAS_NORTE.md`). **Toca MongoDB y la carga →
  TDD obligatorio** (regla global CLAUDE.md).

### C4 — Ajuste diario de caja disponible — SEVERIDAD MEDIA (parcial)

- **Estado real:** La **conciliación por banco y el cierre** existen y son sólidos.
  Falta el **ajuste diario editable** de la caja disponible (el segundo dato que el
  CEO dijo que se carga a diario, `.planning/PROJECT.md §2`).
- **Evidencia:**
  - Existe: `backend/app/cierre/service.py::conciliacion()` (compute-only por banco,
    `R_M` vs `C_M`) y `confirmar_cierre()` (re-ancla `saldo_inicial(M+1) := R_M`).
  - **Falta:** El saldo/caja solo se fija en la **apertura** (`ciclo/router.py::
    abrir_mes`, `saldo_inicial_caja` + `saldos_banco`) y se re-ancla en el **cierre**.
    No hay endpoint para **actualizar el saldo reportado durante el mes en curso**.
    `ciclo/router.py:6-8` lo dice explícito: "El saldo inicial NO se edita por aquí
    después (eso es `ciclo:config` + step-up MFA, **incremento futuro**)". No hay
    `PATCH /meses/{mes}` ni endpoint para reajustar `saldos_banco`.
- **Impacto:** El requisito del norte "ajustar/corregir constantemente para que la
  info **siempre cuadre**" no se cumple intra-mes: la conciliación usa el saldo
  reportado en la apertura; si el banco cambia entre apertura y cierre, no hay dónde
  actualizarlo salvo reabrir. Degrada la exactitud de la caja disponible del día.
- **Fix approach:** Endpoint `PATCH /api/v1/meses/{mes}/saldos` (o `/caja`) para
  registrar el saldo reportado de un banco con `fecha_reporte`, append-only con
  auditoría, sin tocar meses cerrados (regla 4). Reusa `_conciliar()`. RBAC §2.4.

### C7 — Capa predictiva (proyección de caja) — SEVERIDAD ALTA (el valor final)

- **Estado real:** **No existe.** Es el objetivo declarado del producto y hoy no hay
  ningún módulo de proyección.
- **Evidencia:** No hay módulo `proyeccion/`, `prediccion/` ni equivalente en
  `backend/app/`. El único cálculo "hacia adelante" es el **sugerido del mes
  siguiente** (`presupuesto/motor.py`, fórmula histórica §1.4.1), que es
  presupuesto, **no proyección de caja**. No hay: proyección de flujo de caja a
  futuro, objetivos de venta para sostenibilidad, fecha de pago a proveedores, ni
  seguimiento/optimización de IVA (los 4 objetivos de largo plazo del norte).
- **Impacto:** Es **el valor final** del norte ("garantizar superar el umbral de caja
  de mayo 2027", objetivos de venta, fecha pago proveedores, IVA mínimo). Sin C7 el
  sistema solo registra el pasado (lo que el norte explícitamente dice que NO es el
  objetivo). Depende de C3 (datos clasificados) para tener insumo confiable.
- **Fix approach:** Fase 1.5+ dedicada. El molde funcional es `Dashboard
  Artefacto.jsx` + `Flujo de pagos deudas.xlsx` (hojas Proyección / Pagos semana /
  Flujo pago deudas). Recaudo proyectado **discriminado cuota inicial vs cuota de
  crédito** (memoria: diseño-frontend). Todo cálculo financiero en backend (regla 1).

### C8 — Preservación durable del original (M-04) — SEVERIDAD ALTA (bloquea carga real)

- **Estado real:** Solo preservación **local interina** (`ORIGINALES_DIR`). S3 está
  **declarado pero sin cablear** (placeholders de config, cero código).
- **Evidencia:**
  - `backend/app/config.py:63-74`: `originales_dir` documentado como "puente de
    DESARROLLO; en Render el disco es efímero". `aws_access_key_id`,
    `aws_secret_access_key`, `s3_bucket` existen como settings **opcionales**.
  - `backend/app/cargas/service.py:132-137` copia el archivo a disco local
    (`shutil.copy2`) y setea `archivo_s3_key = f"local://{destino}"`. El parámetro
    `archivo_s3_key` existe en la firma pero **el router nunca lo pasa**
    (`cargas/router.py:80-86` solo pasa `dir_originales=settings.originales_dir`).
  - **No hay `boto3`/cliente S3 en el código:** grep `boto3|import boto|put_object|
    upload_file` en `backend/` → 0 resultados; no está en dependencias
    (`pyproject.toml`). La regla dura `OriginalNoPreservableError`
    (`service.py:107-112`) obliga un destino, hoy solo satisfecho por disco efímero.
- **Impacto:** **Bloquea la carga real por la app** (norte: "toda la data es
  persistente desde el inicio", "carga con preservación durable del original,
  S3/Object Lock"). En Render el disco es efímero → el original se pierde en el
  próximo deploy; incumple M-04 (re-procesabilidad). Bloquea la migración de Global66
  abr–jul (`.planning/PROJECT.md §5`).
- **Fix approach:** **Decisión pendiente del CEO: GridFS-en-Mongo (recomendado en
  PROJECT.md, sin infra nueva) vs S3 SISMO.** Una vez decidido: implementar el
  backend de preservación, pasar la clave real (`archivo_s3_key` o id GridFS) desde el
  router, y endurecer `permitir_sin_preservar=False` fuera de dev.

---

## Deuda técnica registrada (del gate Kimi Sprint 4)

### S4-00 — `acotar_linea` sin transacción Mongo (higiene) — SEVERIDAD BAJA

- **Descripción:** `acotar_linea` muta **dos documentos secuencialmente sin
  transacción multi-doc**: `ln.save()` (línea + ajuste) y luego `mc.save()` (estado
  `sugerido→propuesto`), cubierto por una saga compensatoria (O1) en vez de por una
  transacción atómica.
- **Evidencia:** `backend/app/presupuesto/service.py:13` ("No es transacción Mongo
  (afecta pocos docs secuenciales)") y `:200-232` — `await ln.save()` (200),
  `await mc.save()` (206), y el bloque `except` que revierte manualmente (227-232).
- **Impacto:** Ventana de inconsistencia si el proceso muere entre los dos `save`
  (la saga solo compensa fallos del `emit_audit`, no una caída de proceso). Riesgo
  bajo: pocos docs, y el estado converge en el siguiente acotamiento.
- **Fix approach:** Envolver `ln.save` + `mc.save` en `with_transaction` como ya
  hacen `aprobar_presupuesto` y `confirmar_cierre`. Backport de higiene.

### S4-06 — TOCTOU en el cierre + test de step-up en reabrir — SEVERIDAD MEDIA

- **Descripción:** Dos hallazgos Kimi diferidos (B-2 y B-3 del CERTIFICADO):
  1. **TOCTOU (B-2):** las guardas de estado de `confirmar_cierre` se evalúan
     **fuera** de la transacción; deberían **releerse dentro de la sesión**.
  2. **Test nit (B-3):** falta el test que **fija** que `POST /reabrir` exige step-up
     MFA (admin sin MFA reciente → rechazado).
- **Evidencia:**
  - `planning/phases/sprint4-cierre-conciliacion/auditorias/PR1-I/CERTIFICADO.md:26-31`
    (B-2 TOCTOU "releer `mc.estado` dentro de la sesión", B-3 test step-up).
  - `backend/app/cierre/service.py:163-197`: chequeos de `mc.estado` /
    `siguiente.estado` **antes** de `client.start_session()` (228); dentro de
    `_cerrar` (199-226) no se re-lee el estado.
  - Mitigación parcial ya presente: `cierre/router.py:105` sí exige
    `require_step_up()` en reabrir (el control existe; **falta el test que lo blinde**
    contra regresión).
- **Impacto:** Dos cierres/reaperturas concurrentes podrían pasar las guardas y operar
  sobre un estado que cambió entre el check y la transacción (doble ajuste / re-ancla
  inconsistente). Baja probabilidad (1 sola persona opera hoy), pero toca dinero y
  cierre de mes (flujo crítico regla 8).
- **Fix approach:** Releer `mc`/`siguiente` con `session=` dentro de `_cerrar` y
  revalidar estado ahí (abortar la transacción si cambió). Añadir el test de step-up
  en `backend/tests/` (admin sin `mfa_at` reciente → 401/403 en `/reabrir`).

---

## Test Coverage Gaps

- **Auto-clasificación / reclasificación (C3):** sin código → sin tests. Cuando se
  implemente, es zona TDD-obligatoria (toca MongoDB + carga).
- **Step-up en reabrir (S4-06/B-3):** el control existe en `cierre/router.py:105`
  pero **sin test** que lo fije. Riesgo: una refactorización podría quitar el
  `require_step_up` sin que CI lo note.
- **Preservación durable real (C8):** los tests actuales solo cubren el puente local /
  `permitir_sin_preservar`; no hay test del backend durable (GridFS/S3) porque no
  existe aún.

---

*Concerns audit: 2026-07-22*
