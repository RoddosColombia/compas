# EVIDENCIA — sprint4-categorias · I-PR1: C1 categorías administrables

**PR:** #24 `feat/c1-rubros` → `main` · commit `9020932` · 2026-07-22

## 1. Salidas de tests (reales, locales)

### Suite completa del backend
```
354 passed, 34 skipped, 1919 warnings in 242.26s (0:04:02)
```
(34 skipped = requires_real_mongo; cubiertos por el job backend-real-mongo del CI, VERDE en el run del PR #24: https://github.com/RoddosColombia/compas/actions/runs/29968740989)

### Tests de C1 (rubros + catálogo + RBAC + semilla)
```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
71 passed, 742 warnings in 48.82s
```

### B-2 (guardas de la baja) en los módulos existentes
```
tests/test_presupuesto_generar.py tests/test_control.py tests/test_transacciones_manual.py
36 passed, 734 warnings in 51.11s
```

### Lint/format
```
ruff check .   → All checks passed!
ruff format --check . → 112 files already formatted
```

### CI del PR #24
gitleaks ✅ · pip-audit ✅ · runtime-imports ✅ · frontend ✅ · **backend-real-mongo ✅** (índice único (grupo,nombre) + transacciones multi-doc contra replica set real) · backend (en curso al momento de empaquetar; visible en el PR)

## 2. Diff completo del código (backend/app, backend/tests, migrations)

```diff
diff --git a/backend/app/api/v1/__init__.py b/backend/app/api/v1/__init__.py
index 94e3ebe..5288902 100644
--- a/backend/app/api/v1/__init__.py
+++ b/backend/app/api/v1/__init__.py
@@ -10,6 +10,7 @@ from app.ciclo.router import router as ciclo_router
 from app.cierre.router import router as cierre_router
 from app.control.router import router as control_router
 from app.presupuesto.router import router as presupuesto_router
+from app.rubros.router import router as rubros_router
 from app.transacciones.router import router as transacciones_router
 
 api_router = APIRouter()
@@ -20,4 +21,5 @@ api_router.include_router(ciclo_router)
 api_router.include_router(cierre_router)
 api_router.include_router(control_router)
 api_router.include_router(presupuesto_router)
+api_router.include_router(rubros_router)
 api_router.include_router(transacciones_router)
diff --git a/backend/app/audit/events.py b/backend/app/audit/events.py
index 7146276..29e6a84 100644
--- a/backend/app/audit/events.py
+++ b/backend/app/audit/events.py
@@ -1,9 +1,12 @@
 # backend/app/audit/events.py
-"""Catálogo CERRADO de eventos de auditoría (regla 11 / Spec §1.11 / CR-001 / CR-S2).
+"""Catálogo CERRADO de eventos de auditoría (regla 11 / Spec §1.11 / CR-001 /
+CR-S2 / CR-S4).
 
 29 del Spec §1.11 (10 v1.0 + 12 v1.1 + 7 v1.1.1) + `extracto.cargado` (CR-001)
 + `transaccion.creada` (CR-S2 — Kimi M-1 sprint2-cargas: rastro forense permanente
-del POST manual, la única vía de dinero sin archivo de banco) = 31.
+del POST manual, la única vía de dinero sin archivo de banco)
++ `rubro.creado`/`rubro.editado` (CR-S4 — C1 categorías administrables, GO Kimi
+PLAN-I 9.2; `rubro.desactivado` ya venía en v1.0, por eso CR-S4 es +2) = 33.
 NO se inventan eventos sin CR. El nombre del miembro usa `_`; el valor usa
 `<dominio>.<acción>`."""
 
@@ -49,9 +52,13 @@ class AuditEvento(StrEnum):
     # ── CR-001 (1) ──
     extracto_cargado = "extracto.cargado"
 
-    # ── CR-S2 (1) → total 31 ──
+    # ── CR-S2 (1) ──
     transaccion_creada = "transaccion.creada"
 
+    # ── CR-S4 (2) → total 33 (C1 categorías administrables) ──
+    rubro_creado = "rubro.creado"
+    rubro_editado = "rubro.editado"
 
-# Conjunto de los 31 valores canónicos (para validación/tests de completitud).
+
+# Conjunto de los 33 valores canónicos (para validación/tests de completitud).
 CATALOGO_EVENTOS: frozenset[str] = frozenset(e.value for e in AuditEvento)
diff --git a/backend/app/auth/permissions.py b/backend/app/auth/permissions.py
index ebe0a79..6de219c 100644
--- a/backend/app/auth/permissions.py
+++ b/backend/app/auth/permissions.py
@@ -22,6 +22,8 @@ PERMISSIONS: dict[str, frozenset[Role]] = {
     "facturas_emitidas:gestionar": frozenset({Role.financiero, Role.admin}),
     "evidencia:ver": frozenset({Role.financiero, Role.admin}),
     "capacidad_pago:ver": frozenset({Role.financiero, Role.directivo, Role.admin}),
+    # ── CR-S4 (C1 categorías administrables, GO Kimi PLAN-I 9.2) ──
+    "rubros:gestionar": frozenset({Role.financiero, Role.admin}),
     # ── Spec §2.4 (autoridad del ciclo mensual — manda sobre §4.1) ──
     "ciclo:abrir": frozenset({Role.financiero, Role.directivo, Role.admin}),
     "ciclo:proponer": frozenset({Role.financiero, Role.directivo, Role.admin}),
diff --git a/backend/app/domain/rubro.py b/backend/app/domain/rubro.py
index ab76ee1..decf673 100644
--- a/backend/app/domain/rubro.py
+++ b/backend/app/domain/rubro.py
@@ -1,12 +1,16 @@
 # backend/app/domain/rubro.py
-"""Rubro (Spec §1.2) + semilla real del Excel congelado.
-
-La semilla NO es de juguete: sale de `Flujo de pagos deudas.xlsx` (hoja
-'Presupuesto', fuente de verdad del negocio, PRD M1). Son las 31 categorías reales
-de RODDOS agrupadas en los 5 grupos + 2 rubros de sistema que no viven en el Excel:
-'Ajuste de conciliación' (cierre de mes, Spec §2.2.6) y 'Recaudo' (tipo INGRESO,
-Kimi B-1/S0B-05: destino de los abonos de cuotas, PRD M7). En total 33 rubros;
-3 de sistema ('Por clasificar', 'Ajuste de conciliación', 'Recaudo'), inmutables.
+"""Rubro (Spec §1.2) + semilla real de la taxonomía del negocio.
+
+La semilla NO es de juguete: es la taxonomía REAL de `docs/modelo/MODELO.md`
+(destilada de la hoja 'Base real egresos' de `Flujo de pagos deudas.xlsx`) — re-seed
+C1, GO Kimi PLAN-I 9.2. Son las 31 categorías reales de RODDOS en los 5 grupos + 3
+rubros de sistema inmutables: 'Por clasificar' (Spec §1.2), 'Ajuste de conciliación'
+(cierre de mes, Spec §2.2.6) y 'Recaudo' (tipo INGRESO, Kimi B-1/S0B-05: destino de
+los abonos de cuotas, PRD M7). En total 34 rubros.
+
+D3 (gate C1): las categorías viejas de la semilla anterior que ya existan en la BD
+NO se tocan ($setOnInsert) ni se borran — el CEO las depura desde la app (C1). El
+re-seed reporta las colisiones (B-4, ver `seed.py::seed_rubros_reporte`).
 """
 
 from enum import StrEnum
@@ -64,34 +68,38 @@ class Rubro(Document):
 
 
 def _seed() -> list[dict]:
-    """Catálogo real en el orden de la vista Control del Excel; `orden` global 1..32."""
+    """Taxonomía real de MODELO.md ('Base real egresos'); `orden` global 1..34.
+
+    Los 3 de sistema viven en 'otros' — MISMA llave (grupo,nombre) que los docs ya
+    sembrados en prod: el $setOnInsert los reconoce y no los duplica."""
     G = RubroGrupo
     por_grupo: list[tuple[RubroGrupo, list[str]]] = [
         (G.COSTO_PRODUCTO, ["Producto", "SOAT/Matrículas", "Seguros (Hunter)"]),
         (
             G.OPERACION,
             [
-                "Arriendos",
-                "Tecnología y software",
-                "Mobiliario/planta/equipo",
-                "Servicios públicos y telecom",
-                "Mercado y aseo",
-                "Cafetería",
                 "Transporte/peajes/combustible/parqueo",
+                "Cafetería",
+                "Mercado y aseo",
+                "Tecnología y software",
+                "Gastos de representación",
                 "Papelería",
                 "Marketing y publicidad",
-                "Gastos de representación",
-                "Renting",
+                "Servicios públicos y telecom",
+                "Mobiliario/planta/equipo",
+                "Viajes corporativos",
+                "Grúas y traslados",
+                "Dotación empleados",
+                "Freelance",
             ],
         ),
         (
             G.NOMINA,
             [
-                "Sueldos empleados",
                 "Sueldos directivos",
+                "Sueldos empleados",
                 "Bonificaciones",
                 "Beneficios Heads",
-                "Planillas nuevas",
                 "Planillas anteriores",
             ],
         ),
@@ -99,25 +107,23 @@ def _seed() -> list[dict]:
             G.DEUDAS_OBLIGACIONES,
             [
                 "Préstamos",
-                "Deudas tarjetas de crédito",
-                "Garantía cupo",
-                "Deudas impuestos",
                 "Deudas proveedores anteriores",
+                "Deudas tarjetas de crédito",
             ],
         ),
         (
             G.OTROS,
             [
+                "Impuestos",
                 "Otros gastos",
-                "Gastos notariales",
                 "Gastos bancarios",
                 "Gastos financieros",
-                "Impuestos",
-                "Por clasificar",  # de sistema (Spec §1.2)
+                "Asuntos legales",
+                "Gastos notariales",
+                "Arriendos",  # MODELO.md lo ubica en OTROS (antes: operación)
             ],
         ),
     ]
-    sistema = {"Por clasificar"}
     filas: list[dict] = []
     orden = 0
     for grupo, nombres in por_grupo:
@@ -130,36 +136,29 @@ def _seed() -> list[dict]:
                     "tipo_flujo": "egreso",
                     "orden": orden,
                     "activo": True,
-                    "es_sistema": nombre in sistema,
+                    "es_sistema": False,
                 }
             )
-    # 'Ajuste de conciliación': de sistema, exigido por el cierre (Spec §2.2.6);
-    # no vive en el Excel. Grupo 'otros'.
-    orden += 1
-    filas.append(
-        {
-            "grupo": G.OTROS.value,
-            "nombre": "Ajuste de conciliación",
-            "tipo_flujo": "egreso",
-            "orden": orden,
-            "activo": True,
-            "es_sistema": True,
-        }
-    )
-    # 'Recaudo': de sistema, tipo INGRESO (Kimi B-1 / S0B-05). Destino de los
-    # abonos de cuotas (regla PRD M7 'Abono' → ingreso recaudo); sin él, la
-    # clasificación automática de ingresos no tiene rubro. Tampoco vive en el Excel.
-    orden += 1
-    filas.append(
-        {
-            "grupo": G.OTROS.value,
-            "nombre": "Recaudo",
-            "tipo_flujo": "ingreso",
-            "orden": orden,
-            "activo": True,
-            "es_sistema": True,
-        }
-    )
+    # ── Rubros de sistema (inmutables; no viven en el Excel salvo Por clasificar) ──
+    # 'Por clasificar' (Spec §1.2): destino de todo movimiento sin clasificar.
+    # 'Ajuste de conciliación' (Spec §2.2.6): exigido por el cierre de mes.
+    # 'Recaudo' (Kimi B-1/S0B-05): INGRESO, destino de los abonos de cuotas (PRD M7).
+    for nombre, tipo in [
+        ("Por clasificar", "egreso"),
+        ("Ajuste de conciliación", "egreso"),
+        ("Recaudo", "ingreso"),
+    ]:
+        orden += 1
+        filas.append(
+            {
+                "grupo": G.OTROS.value,
+                "nombre": nombre,
+                "tipo_flujo": tipo,
+                "orden": orden,
+                "activo": True,
+                "es_sistema": True,
+            }
+        )
     return filas
 
 
diff --git a/backend/app/domain/seed.py b/backend/app/domain/seed.py
index 767a651..a658f8a 100644
--- a/backend/app/domain/seed.py
+++ b/backend/app/domain/seed.py
@@ -33,8 +33,13 @@ def _a_bson(v: Any) -> Any:
 
 async def _upsert_muchos(
     db: Any, coleccion: str, filas: list[dict], llave: list[str]
-) -> int:
+) -> tuple[int, list[dict]]:
+    """Upsert idempotente. Devuelve (insertados, colisiones) — B-4 (Kimi PLAN-I C1):
+    cada llave donde $setOnInsert OMITIÓ por doc preexistente se reporta con el doc
+    existente y lo que la semilla habría puesto, para verificación manual (un doc
+    viejo con tipo_flujo/orden distintos ya no pasa en silencio)."""
     insertados = 0
+    colisiones: list[dict] = []
     col = db[coleccion]
     for fila in filas:
         filtro = {k: fila[k] for k in llave}
@@ -42,11 +47,25 @@ async def _upsert_muchos(
         res = await col.update_one(filtro, {"$setOnInsert": doc}, upsert=True)
         if res.upserted_id is not None:
             insertados += 1
-    return insertados
+        else:
+            existente = await col.find_one(filtro, {"_id": 0})
+            colisiones.append({**filtro, "existente": existente, "semilla": fila})
+    return insertados, colisiones
 
 
 async def seed_rubros(db: Any) -> int:
-    """Inserta las 33 categorías (31 del Excel + 2 de sistema; idempotente)."""
+    """Inserta las 34 categorías (31 reales de MODELO.md + 3 de sistema;
+    idempotente). Compat: devuelve solo el conteo — el reporte B-4 está en
+    `seed_rubros_reporte`."""
+    insertados, _ = await _upsert_muchos(
+        db, RUBROS_COLLECTION, SEMILLA_RUBROS, ["grupo", "nombre"]
+    )
+    return insertados
+
+
+async def seed_rubros_reporte(db: Any) -> tuple[int, list[dict]]:
+    """Como `seed_rubros`, pero devuelve también el reporte de colisiones (B-4).
+    Lo usa la migración del re-seed C1."""
     return await _upsert_muchos(
         db, RUBROS_COLLECTION, SEMILLA_RUBROS, ["grupo", "nombre"]
     )
@@ -54,6 +73,7 @@ async def seed_rubros(db: Any) -> int:
 
 async def seed_configuracion(db: Any) -> int:
     """Inserta las claves iniciales (idempotente por (clave, vigente_desde))."""
-    return await _upsert_muchos(
+    insertados, _ = await _upsert_muchos(
         db, CONFIGURACION_COLLECTION, SEMILLA_CONFIGURACION, ["clave", "vigente_desde"]
     )
+    return insertados
diff --git a/backend/app/rubros/__init__.py b/backend/app/rubros/__init__.py
new file mode 100644
index 0000000..c44f455
--- /dev/null
+++ b/backend/app/rubros/__init__.py
@@ -0,0 +1 @@
+# backend/app/rubros/__init__.py
diff --git a/backend/app/rubros/router.py b/backend/app/rubros/router.py
new file mode 100644
index 0000000..e343cd7
--- /dev/null
+++ b/backend/app/rubros/router.py
@@ -0,0 +1,138 @@
+# backend/app/rubros/router.py
+"""/api/v1/rubros — C1 categorías administrables (CR-S4, GO Kimi PLAN-I 9.2).
+
+MARCADO PARA AUDITORÍA KIMI (gate I-PR1).
+
+RBAC: GET con `dashboard:leer` (los 4 roles); mutaciones con `rubros:gestionar`
+(= {financiero, admin}, CR-S4) + `verify_origin` (anti-CSRF). Sin Idempotency-Key:
+no es movimiento de dinero (§1.12 aplica a POST de dinero); el índice único
+(grupo,nombre) hace inocuo el replay del POST de creación (→ 409)."""
+
+from fastapi import APIRouter, Depends, HTTPException, Query
+from pydantic import BaseModel, ConfigDict, Field, field_validator
+
+from app.auth.deps import require_permission
+from app.auth.models import User
+from app.auth.router import verify_origin
+from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
+from app.rubros import service
+
+router = APIRouter(prefix="/rubros", tags=["rubros"])
+
+
+class RubroCrearBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    grupo: RubroGrupo
+    nombre: str = Field(min_length=1, max_length=80)
+    tipo_flujo: TipoFlujo = TipoFlujo.EGRESO
+
+    @field_validator("grupo", mode="before")
+    @classmethod
+    def _cast_grupo(cls, v: object) -> object:
+        # strict=True no coerciona str→StrEnum; valor inválido → ValueError → 422.
+        return v if isinstance(v, RubroGrupo) else RubroGrupo(v)
+
+    @field_validator("tipo_flujo", mode="before")
+    @classmethod
+    def _cast_tipo(cls, v: object) -> object:
+        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)
+
+
+class RubroEditarBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    nombre: str | None = Field(default=None, min_length=1, max_length=80)
+    orden: int | None = None
+    tipo_flujo: TipoFlujo | None = None
+    activo: bool | None = None  # solo true (reactivar, B-3); false → 422
+
+    @field_validator("tipo_flujo", mode="before")
+    @classmethod
+    def _cast_tipo(cls, v: object) -> object:
+        if v is None or isinstance(v, TipoFlujo):
+            return v
+        return TipoFlujo(v)
+
+
+def _serializar(r: Rubro) -> dict:
+    return {
+        "id": str(r.id),
+        "grupo": r.grupo.value,
+        "nombre": r.nombre,
+        "tipo_flujo": r.tipo_flujo.value,
+        "orden": r.orden,
+        "activo": r.activo,
+        "es_sistema": r.es_sistema,
+    }
+
+
+def _parse_grupo(grupo: str | None) -> RubroGrupo | None:
+    if grupo is None:
+        return None
+    try:
+        return RubroGrupo(grupo)
+    except ValueError:
+        raise HTTPException(422, f"grupo inválido: '{grupo}'") from None
+
+
+@router.get("")
+async def listar(
+    activo: bool | None = Query(default=None),
+    grupo: str | None = Query(default=None),
+    _: User = Depends(require_permission("dashboard:leer")),
+):
+    rubros = await service.listar_rubros(activo=activo, grupo=_parse_grupo(grupo))
+    return [_serializar(r) for r in rubros]
+
+
+@router.post("", status_code=201)
+async def crear(
+    body: RubroCrearBody,
+    user: User = Depends(require_permission("rubros:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        rubro = await service.crear_rubro(
+            grupo=body.grupo,
+            nombre=body.nombre,
+            tipo_flujo=body.tipo_flujo,
+            usuario_id=user.id,
+        )
+    except service.RubrosError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(rubro)
+
+
+@router.patch("/{rubro_id}")
+async def editar(
+    rubro_id: str,
+    body: RubroEditarBody,
+    user: User = Depends(require_permission("rubros:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        rubro = await service.editar_rubro(
+            rubro_id=rubro_id,
+            usuario_id=user.id,
+            nombre=body.nombre,
+            orden=body.orden,
+            tipo_flujo=body.tipo_flujo,
+            activo=body.activo,
+        )
+    except service.RubrosError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(rubro)
+
+
+@router.post("/{rubro_id}/desactivar")
+async def desactivar(
+    rubro_id: str,
+    user: User = Depends(require_permission("rubros:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        rubro = await service.desactivar_rubro(rubro_id=rubro_id, usuario_id=user.id)
+    except service.RubrosError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(rubro)
diff --git a/backend/app/rubros/service.py b/backend/app/rubros/service.py
new file mode 100644
index 0000000..31dda03
--- /dev/null
+++ b/backend/app/rubros/service.py
@@ -0,0 +1,245 @@
+# backend/app/rubros/service.py
+"""C1 categorías administrables (CR-S4, GO Kimi PLAN-I 9.2): CRUD de rubros.
+
+MARCADO PARA AUDITORÍA KIMI (estructura del sistema presupuestal; gate I-PR1).
+
+Decisiones fijadas en el gate del PLAN:
+  - D1/B-1: `tipo_flujo` se CONGELA si el rubro tiene referencias — no solo
+    transacciones: ∃ Transaccion(rubro_id) ∨ ∃ PresupuestoLinea(rubro_id). Voltear
+    el tipo dejaría una línea calculada como egreso siendo ingreso (integridad
+    semántica, regla 4 en espíritu). Nombre/orden editables siempre (no afectan
+    cómputo).
+  - D2: la baja es LÓGICA (`activo=false`); el histórico queda intacto y visible.
+    Alcance de la baja (B-2): (a) la clasificación rechaza rubros inactivos — la
+    guarda vive en `transacciones/service.py::crear_transaccion_manual` (y aplicará
+    a C3); (b) el motor del sugerido ya omite inactivos (filtro `activo==True` en
+    `presupuesto/service.py::generar_sugerido`); (c) la Vista Control CONSERVA las
+    líneas ya existentes del rubro inactivo (itera por líneas). Nota: una categoría
+    de tipo INGRESO no recibe línea de presupuesto (el presupuesto §1.4 es de
+    egresos) — no esperarla en Vista Control.
+  - B-3: reactivar = PATCH `activo:true` → emite `rubro.editado` {activo:
+    false→true} (rastro completo sin un 34.º evento). PATCH `activo:false` → 422:
+    la baja va por POST /desactivar (evento `rubro.desactivado` propio).
+  - B-5: auditoría FAIL-CLOSED estilo O1 — mutar → emitir → si el emit falla,
+    COMPENSAR (borrar el rubro creado / revertir los campos) y propagar. Es un solo
+    documento: la compensación es trivial y consistente con el estándar del ciclo.
+  - Rubros de sistema (`es_sistema`): inmutables — PATCH y desactivar → 409.
+  - Único (grupo, nombre): pre-check (mongomock) + DuplicateKeyError del índice
+    real → 409, nunca 500.
+"""
+
+from beanie import PydanticObjectId
+from pymongo.errors import DuplicateKeyError
+
+from app.audit.events import AuditEvento
+from app.audit.service import emit_audit
+from app.domain.presupuesto import PresupuestoLinea
+from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
+from app.domain.transaccion import Transaccion
+
+
+class RubrosError(Exception):
+    def __init__(self, detalle: str, status: int = 422) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+        self.status = status
+
+
+async def _obtener(rubro_id: str) -> Rubro:
+    try:
+        rid = PydanticObjectId(rubro_id)
+    except Exception:
+        raise RubrosError("rubro_id inválido", 422) from None
+    r = await Rubro.get(rid)
+    if r is None:
+        raise RubrosError("el rubro no existe", 404)
+    return r
+
+
+async def _tiene_referencias(rubro_id: PydanticObjectId) -> bool:
+    """B-1: referencias = transacciones O líneas de presupuesto (no solo
+    movimientos). Consulta cruda con proyección {_id:1}: solo importa la
+    EXISTENCIA — no pagar el parse del Document completo."""
+    tx = await Transaccion.get_pymongo_collection().find_one(
+        {"rubro_id": rubro_id}, {"_id": 1}
+    )
+    if tx is not None:
+        return True
+    ln = await PresupuestoLinea.get_pymongo_collection().find_one(
+        {"rubro_id": rubro_id}, {"_id": 1}
+    )
+    return ln is not None
+
+
+async def listar_rubros(
+    *, activo: bool | None = None, grupo: RubroGrupo | None = None
+) -> list[Rubro]:
+    filtros = []
+    if activo is not None:
+        filtros.append(Rubro.activo == activo)
+    if grupo is not None:
+        filtros.append(Rubro.grupo == grupo)
+    return await Rubro.find(*filtros).sort(+Rubro.orden).to_list()
+
+
+async def crear_rubro(
+    *,
+    grupo: RubroGrupo,
+    nombre: str,
+    tipo_flujo: TipoFlujo,
+    usuario_id: str,
+) -> Rubro:
+    """POST: crea con `orden` = máx(grupo)+1 y emite `rubro.creado` (fail-closed)."""
+    if await Rubro.find_one(Rubro.grupo == grupo, Rubro.nombre == nombre) is not None:
+        raise RubrosError(
+            f"ya existe un rubro '{nombre}' en el grupo '{grupo.value}'", 409
+        )
+    ultimo = await Rubro.find(Rubro.grupo == grupo).sort(-Rubro.orden).first_or_none()
+    rubro = Rubro(
+        grupo=grupo,
+        nombre=nombre,
+        tipo_flujo=tipo_flujo,
+        orden=(ultimo.orden if ultimo is not None else 0) + 1,
+    )
+    try:
+        await rubro.insert()
+    except DuplicateKeyError:
+        # Carrera real: el índice único (grupo,nombre) atrapa al 2º → 409, no 500.
+        raise RubrosError(
+            f"ya existe un rubro '{nombre}' en el grupo '{grupo.value}'", 409
+        ) from None
+
+    try:
+        await emit_audit(
+            AuditEvento.rubro_creado,
+            entidad="rubro",
+            entidad_id=str(rubro.id),
+            actor_id=usuario_id,
+            metadata={
+                "grupo": grupo.value,
+                "nombre": nombre,
+                "tipo_flujo": tipo_flujo.value,
+                "orden": rubro.orden,
+            },
+        )
+    except Exception:
+        # B-5 (saga O1): sin rastro no hay cambio estructural → compensar.
+        await rubro.delete()
+        raise
+    return rubro
+
+
+async def editar_rubro(
+    *,
+    rubro_id: str,
+    usuario_id: str,
+    nombre: str | None = None,
+    orden: int | None = None,
+    tipo_flujo: TipoFlujo | None = None,
+    activo: bool | None = None,
+) -> Rubro:
+    """PATCH: edita nombre/orden/tipo_flujo y reactiva (B-3). Emite `rubro.editado`
+    con {campo: {anterior, nuevo}} (fail-closed B-5)."""
+    rubro = await _obtener(rubro_id)
+    if rubro.es_sistema:
+        raise RubrosError(
+            f"'{rubro.nombre}' es un rubro de sistema y es inmutable (§2.2)", 409
+        )
+
+    cambios: dict[str, dict] = {}
+    previos: dict[str, object] = {}
+
+    if activo is not None:
+        if activo is False:
+            raise RubrosError("la baja va por POST /rubros/{id}/desactivar (B-3)", 422)
+        if not rubro.activo:
+            previos["activo"] = rubro.activo
+            cambios["activo"] = {"anterior": False, "nuevo": True}
+            rubro.activo = True
+
+    if tipo_flujo is not None and tipo_flujo is not rubro.tipo_flujo:
+        if await _tiene_referencias(rubro.id):
+            raise RubrosError(
+                "tipo_flujo está congelado: el rubro tiene transacciones o líneas "
+                "de presupuesto (D1/B-1)",
+                409,
+            )
+        previos["tipo_flujo"] = rubro.tipo_flujo
+        cambios["tipo_flujo"] = {
+            "anterior": rubro.tipo_flujo.value,
+            "nuevo": tipo_flujo.value,
+        }
+        rubro.tipo_flujo = tipo_flujo
+
+    if nombre is not None and nombre != rubro.nombre:
+        existe = await Rubro.find_one(
+            Rubro.grupo == rubro.grupo, Rubro.nombre == nombre
+        )
+        if existe is not None:
+            raise RubrosError(
+                f"ya existe un rubro '{nombre}' en el grupo '{rubro.grupo.value}'",
+                409,
+            )
+        previos["nombre"] = rubro.nombre
+        cambios["nombre"] = {"anterior": rubro.nombre, "nuevo": nombre}
+        rubro.nombre = nombre
+
+    if orden is not None and orden != rubro.orden:
+        previos["orden"] = rubro.orden
+        cambios["orden"] = {"anterior": rubro.orden, "nuevo": orden}
+        rubro.orden = orden
+
+    if not cambios:
+        raise RubrosError("nada que editar (ningún campo cambia)", 422)
+
+    try:
+        await rubro.save()
+    except DuplicateKeyError:
+        raise RubrosError(
+            f"ya existe un rubro '{rubro.nombre}' en el grupo '{rubro.grupo.value}'",
+            409,
+        ) from None
+
+    try:
+        await emit_audit(
+            AuditEvento.rubro_editado,
+            entidad="rubro",
+            entidad_id=str(rubro.id),
+            actor_id=usuario_id,
+            metadata={"cambios": cambios},
+        )
+    except Exception:
+        # B-5 (saga O1): revertir los campos editados y propagar.
+        for campo, valor in previos.items():
+            setattr(rubro, campo, valor)
+        await rubro.save()
+        raise
+    return rubro
+
+
+async def desactivar_rubro(*, rubro_id: str, usuario_id: str) -> Rubro:
+    """POST /desactivar: baja LÓGICA (D2). Emite `rubro.desactivado` (fail-closed)."""
+    rubro = await _obtener(rubro_id)
+    if rubro.es_sistema:
+        raise RubrosError(
+            f"'{rubro.nombre}' es un rubro de sistema y es inmutable (§2.2)", 409
+        )
+    if not rubro.activo:
+        raise RubrosError(f"'{rubro.nombre}' ya está inactivo", 409)
+
+    rubro.activo = False
+    await rubro.save()
+    try:
+        await emit_audit(
+            AuditEvento.rubro_desactivado,
+            entidad="rubro",
+            entidad_id=str(rubro.id),
+            actor_id=usuario_id,
+            metadata={"grupo": rubro.grupo.value, "nombre": rubro.nombre},
+        )
+    except Exception:
+        # B-5 (saga O1): sin rastro no hay baja → revertir.
+        rubro.activo = True
+        await rubro.save()
+        raise
+    return rubro
diff --git a/backend/tests/test_audit_events.py b/backend/tests/test_audit_events.py
index 75406ff..6b3f737 100644
--- a/backend/tests/test_audit_events.py
+++ b/backend/tests/test_audit_events.py
@@ -1,15 +1,17 @@
 # backend/tests/test_audit_events.py
-"""Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001.
+"""Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001 / CR-S2 / CR-S4.
 
 29 (Spec §1.11) + extracto.cargado (CR-001) + transaccion.creada (CR-S2, Kimi
-M-1 sprint2-cargas) = 31. No se inventan eventos sin CR."""
+M-1 sprint2-cargas) + rubro.creado/rubro.editado (CR-S4, C1 categorías
+administrables — `rubro.desactivado` ya venía en v1.0) = 33. No se inventan
+eventos sin CR."""
 
 from app.audit.events import CATALOGO_EVENTOS, AuditEvento
 
 
-def test_catalogo_tiene_exactamente_31_eventos():
-    assert len(AuditEvento) == 31
-    assert len(CATALOGO_EVENTOS) == 31
+def test_catalogo_tiene_exactamente_33_eventos():
+    assert len(AuditEvento) == 33
+    assert len(CATALOGO_EVENTOS) == 33
 
 
 def test_extracto_cargado_es_el_evento_30_de_cr001():
@@ -29,6 +31,9 @@ def test_eventos_clave_presentes():
         "iva_generado.override",
         "factura_emitida.anulada",
         "transaccion.creada",  # CR-S2 (Kimi M-1): rastro forense del POST manual
+        "rubro.creado",  # CR-S4 (C1): alta de categoría desde la app
+        "rubro.editado",  # CR-S4 (C1): edición (incl. reactivación B-3)
+        "rubro.desactivado",  # v1.0: baja lógica (verificado Kimi PLAN-I C1)
     ):
         assert esperado in CATALOGO_EVENTOS
 
diff --git a/backend/tests/test_control.py b/backend/tests/test_control.py
index 17c3547..e50971d 100644
--- a/backend/tests/test_control.py
+++ b/backend/tests/test_control.py
@@ -168,6 +168,22 @@ async def test_bordes_semaforo(api):
         assert f["semaforo"] == sem, nombre
 
 
+async def test_linea_de_rubro_inactivo_se_conserva(api):
+    # B-2c (Kimi PLAN-I C1): desactivar un rubro NO borra su línea del ciclo en
+    # curso — la Vista Control sigue mostrando el histórico (itera por líneas).
+    h = await _token(api)
+    mc = await _mes()
+    ru = await _rubro("Renting")
+    await _linea(mc, ru, "800000")
+    await _tx(mc, ru, "300000")
+    ru.activo = False  # baja lógica DESPUÉS de tener línea + ejecutado
+    await ru.save()
+    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
+    f = _fila(data, str(ru.id))
+    assert f["definido"] == "800000.00"
+    assert f["ejecutado"] == "300000.00"
+
+
 async def test_semaforo_definido_cero(api):
     h = await _token(api)
     mc = await _mes()
diff --git a/backend/tests/test_domain_persistence.py b/backend/tests/test_domain_persistence.py
index 2db6919..216d36d 100644
--- a/backend/tests/test_domain_persistence.py
+++ b/backend/tests/test_domain_persistence.py
@@ -10,7 +10,7 @@ from app.domain import DOMAIN_DOCUMENTS
 from app.domain.configuracion import Configuracion
 from app.domain.mes_control import MesControl
 from app.domain.rubro import Rubro
-from app.domain.seed import seed_configuracion, seed_rubros
+from app.domain.seed import seed_configuracion, seed_rubros, seed_rubros_reporte
 from beanie import init_beanie
 from mongomock_motor import AsyncMongoMockClient
 
@@ -49,16 +49,46 @@ async def test_configuracion_decimal_round_trip(db):
 
 
 async def test_seed_rubros_idempotente(db):
+    # Re-seed C1 (GO Kimi PLAN-I 9.2): 31 reales de MODELO.md + 3 de sistema = 34.
     n1 = await seed_rubros(db)
     total1 = await Rubro.find_all().count()
     n2 = await seed_rubros(db)  # segunda corrida: no debe duplicar
     total2 = await Rubro.find_all().count()
-    assert n1 == 33 and total1 == 33
-    assert n2 == 0 and total2 == 33
+    assert n1 == 34 and total1 == 34
+    assert n2 == 0 and total2 == 34
     sistema = await Rubro.find(Rubro.es_sistema == True).count()  # noqa: E712
     assert sistema == 3
 
 
+async def test_seed_rubros_no_pisa_ediciones(db):
+    # $setOnInsert: un doc existente con la misma llave (grupo,nombre) NO se toca
+    # aunque la semilla traiga otros valores (ediciones del Admin sobreviven).
+    await Rubro(grupo="operacion", nombre="Cafetería", orden=77).insert()
+    await seed_rubros(db)
+    got = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    assert got.orden == 77  # el valor editado sobrevive al re-seed
+
+
+async def test_seed_rubros_reporte_de_colisiones(db):
+    # B-4 (Kimi PLAN-I C1): el re-seed REPORTA los (grupo,nombre) donde
+    # $setOnInsert omitió por doc preexistente — un doc viejo con tipo_flujo/orden
+    # distintos del mapeo de MODELO.md ya no pasa en silencio.
+    await Rubro(
+        grupo="operacion", nombre="Cafetería", orden=77, tipo_flujo="ingreso"
+    ).insert()
+    insertados, colisiones = await seed_rubros_reporte(db)
+    assert insertados == 33  # 34 - 1 preexistente
+    assert len(colisiones) == 1
+    col = colisiones[0]
+    assert (col["grupo"], col["nombre"]) == ("operacion", "Cafetería")
+    # El reporte trae lo EXISTENTE vs lo que la semilla habría puesto (verificable).
+    assert col["existente"]["tipo_flujo"] == "ingreso"
+    assert col["semilla"]["tipo_flujo"] == "egreso"
+    # Corrida limpia posterior: 0 nuevos, todas las llaves ya existen.
+    insertados2, colisiones2 = await seed_rubros_reporte(db)
+    assert insertados2 == 0 and len(colisiones2) == 34
+
+
 async def test_seed_configuracion_idempotente(db):
     await seed_configuracion(db)
     await seed_configuracion(db)
diff --git a/backend/tests/test_domain_rubro.py b/backend/tests/test_domain_rubro.py
index c6148ab..d48ff72 100644
--- a/backend/tests/test_domain_rubro.py
+++ b/backend/tests/test_domain_rubro.py
@@ -40,13 +40,28 @@ def test_nombre_max_80():
         Rubro(grupo="otros", nombre="x" * 81, orden=1)
 
 
-# ---- Semilla real (frozen: Flujo de pagos deudas.xlsx, hoja 'Presupuesto') ----
+# ---- Semilla real (contrato: docs/modelo/MODELO.md, 'Base real egresos') ----
 
 
-def test_semilla_tiene_33_rubros():
-    # 31 categorías del Excel + 'Ajuste de conciliación' (Spec §2.2.6) + 'Recaudo'
-    # (ingreso, Kimi B-1 / S0B-05: destino de los abonos de cuotas, PRD M7)
-    assert len(SEMILLA_RUBROS) == 33
+def test_semilla_tiene_34_rubros():
+    # 31 categorías reales de MODELO.md + los 3 de sistema ('Por clasificar',
+    # 'Ajuste de conciliación' Spec §2.2.6, 'Recaudo' ingreso Kimi B-1/S0B-05).
+    # Re-seed C1 (GO Kimi PLAN-I 9.2): la taxonomía manda MODELO.md.
+    assert len(SEMILLA_RUBROS) == 34
+
+
+def test_semilla_reparto_por_grupo_segun_modelo():
+    # MODELO.md: costo 3 · operación 13 · nómina 5 · deudas 3 · otros 7 (+3 sistema).
+    conteo: dict[str, int] = {}
+    for r in SEMILLA_RUBROS:
+        conteo[r["grupo"]] = conteo.get(r["grupo"], 0) + 1
+    assert conteo == {
+        "costo_producto": 3,
+        "operacion": 13,
+        "nomina": 5,
+        "deudas_obligaciones": 3,
+        "otros": 10,  # 7 reales + 3 de sistema
+    }
 
 
 def test_semilla_cubre_los_cinco_grupos():
@@ -74,7 +89,7 @@ def test_semilla_nombres_unicos_por_grupo():
 
 def test_semilla_ordenes_unicos_y_consecutivos():
     ordenes = sorted(r["orden"] for r in SEMILLA_RUBROS)
-    assert ordenes == list(range(1, 34))
+    assert ordenes == list(range(1, 35))
 
 
 def test_semilla_construye_modelos_validos():
@@ -92,5 +107,18 @@ def test_semilla_incluye_categorias_reales_conocidas():
         "Sueldos directivos",
         "Préstamos",
         "Impuestos",
+        # Nuevas de MODELO.md ('Base real egresos') — re-seed C1:
+        "Viajes corporativos",
+        "Grúas y traslados",
+        "Dotación empleados",
+        "Freelance",
+        "Asuntos legales",
     ):
         assert esperado in nombres, esperado
+
+
+def test_semilla_arriendos_vive_en_otros():
+    # MODELO.md ubica 'Arriendos' en OTROS (la semilla vieja lo tenía en operación;
+    # el doc viejo NO se toca — D3: el CEO depura desde la app).
+    arriendos = [r for r in SEMILLA_RUBROS if r["nombre"] == "Arriendos"]
+    assert [r["grupo"] for r in arriendos] == ["otros"]
diff --git a/backend/tests/test_presupuesto_generar.py b/backend/tests/test_presupuesto_generar.py
index f335e09..27113d2 100644
--- a/backend/tests/test_presupuesto_generar.py
+++ b/backend/tests/test_presupuesto_generar.py
@@ -148,6 +148,24 @@ async def test_excluye_rubros_de_sistema(api):
     assert nombres_generados == 1  # solo Arriendos, no los de sistema
 
 
+async def test_excluye_rubros_inactivos(api):
+    # B-2b (Kimi PLAN-I C1): la baja lógica NO "gotea" — un rubro desactivado no
+    # vuelve a recibir línea en generaciones futuras (aunque tenga ejecutado real).
+    h = await _token(api)
+    jun = await _mes("2026-06-01", EstadoMes.CERRADO)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    activo = await _rubro("Arriendos", 4)
+    inactivo = await _rubro("Renting", 5)
+    inactivo.activo = False
+    await inactivo.save()
+    await _ejec(inactivo.id, jun, "9000000")  # con historia y todo, se omite
+    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
+    assert r.status_code == 201
+    rubro_ids = {x["rubro_id"] for x in r.json()["lineas"]}
+    assert str(activo.id) in rubro_ids
+    assert str(inactivo.id) not in rubro_ids
+
+
 async def test_no_regenera_409(api):
     h = await _token(api)
     await _mes("2026-07-01", EstadoMes.SUGERIDO)
diff --git a/backend/tests/test_rbac_permissions.py b/backend/tests/test_rbac_permissions.py
index 31fe2f4..5679bc2 100644
--- a/backend/tests/test_rbac_permissions.py
+++ b/backend/tests/test_rbac_permissions.py
@@ -20,6 +20,8 @@ CANONICA: dict[str, set[Role]] = {
     "facturas_emitidas:gestionar": {Role.financiero, Role.admin},
     "evidencia:ver": {Role.financiero, Role.admin},
     "capacidad_pago:ver": {Role.financiero, Role.directivo, Role.admin},
+    # CR-S4 (C1 categorías administrables): gestión del catálogo de rubros
+    "rubros:gestionar": {Role.financiero, Role.admin},
     # §2.4 — autoridad del ciclo (manda sobre §4.1)
     "ciclo:abrir": {Role.financiero, Role.directivo, Role.admin},
     "ciclo:proponer": {Role.financiero, Role.directivo, Role.admin},
diff --git a/backend/tests/test_rubros_endpoints.py b/backend/tests/test_rubros_endpoints.py
new file mode 100644
index 0000000..6dc3bc8
--- /dev/null
+++ b/backend/tests/test_rubros_endpoints.py
@@ -0,0 +1,528 @@
+# backend/tests/test_rubros_endpoints.py
+"""C1 categorías administrables — /api/v1/rubros (GO Kimi PLAN-I 9.2, CR-S4).
+
+MARCADO PARA AUDITORÍA KIMI (gate de código I-PR1; lista de tests del §5 del
+veredicto PLAN-I).
+
+Reglas cubiertas:
+  - CR-S4: `rubro.creado`/`rubro.editado` (+ `rubro.desactivado` v1.0) y RBAC
+    `rubros:gestionar` = {financiero, admin}; consulta/directivo → 403 en mutar.
+  - Sistema inmutable (§2.2): PATCH y desactivar sobre los 3 rubros de sistema → 409.
+  - D1/B-1: `tipo_flujo` congelado si el rubro tiene Transaccion O PresupuestoLinea
+    (referencias, no solo movimientos); sin referencias → editable.
+  - D2/B-2: baja lógica; desactivar con movimientos → 200 e histórico intacto.
+  - B-3: reactivación = PATCH activo:true → `rubro.editado` {activo false→true};
+    PATCH activo:false → 422 (la baja va por POST /desactivar, evento propio).
+  - B-5: auditoría fail-closed estilo O1 — si el emit falla, se compensa (el rubro
+    creado se borra / el campo editado se revierte).
+  - Único (grupo, nombre) → 409 (pre-check en mongomock; índice real en el gate
+    real-mongo de dedup).
+"""
+
+from decimal import Decimal
+
+import httpx
+import pytest
+import pytest_asyncio
+from app.audit.service import configure_audit, reset_audit
+from app.auth import passwords, repository
+from app.auth.models import User
+from app.auth.roles import Role
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.bancos import Banco
+from app.domain.mes_control import MesControl
+from app.domain.presupuesto import PresupuestoLinea
+from app.domain.rubro import Rubro, TipoFlujo
+from app.domain.transaccion import Transaccion
+from app.main import create_app
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+PWD = "clave-larga-1234"
+
+SISTEMA = ["Por clasificar", "Ajuste de conciliación", "Recaudo"]
+
+
+@pytest_asyncio.fixture
+async def api(monkeypatch):
+    monkeypatch.setenv("APP_ENV", "development")
+    monkeypatch.setenv("JWT_SECRET", "x" * 40)
+    monkeypatch.setenv("COOKIE_SECURE", "False")
+    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+    get_settings.cache_clear()
+
+    app = create_app()
+    # tz_aware=True como el Motor real: los datetime re-leídos vuelven UTC-aware.
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
+    for correo, rol in [
+        ("consulta@roddos.com", Role.consulta),
+        ("fin@roddos.com", Role.financiero),
+        ("dir@roddos.com", Role.directivo),
+        ("admin@roddos.com", Role.admin),
+    ]:
+        await repository.create_user(
+            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
+        )
+    # Semilla mínima: 3 de sistema + 2 operativos.
+    await Rubro(
+        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
+    ).insert()
+    await Rubro(
+        grupo="otros", nombre="Ajuste de conciliación", orden=98, es_sistema=True
+    ).insert()
+    await Rubro(
+        grupo="otros",
+        nombre="Recaudo",
+        tipo_flujo="ingreso",
+        orden=99,
+        es_sistema=True,
+    ).insert()
+    await Rubro(grupo="operacion", nombre="Arriendos", orden=1).insert()
+    await Rubro(grupo="operacion", nombre="Cafetería", orden=2).insert()
+    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()
+
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac, c
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def _token(ac, email="fin@roddos.com") -> dict:
+    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+    assert r.status_code == 200
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+async def _rubro(nombre: str) -> Rubro:
+    r = await Rubro.find_one(Rubro.nombre == nombre)
+    assert r is not None, nombre
+    return r
+
+
+async def _referencia_tx(rubro: Rubro) -> Transaccion:
+    mc = await MesControl.find_one(MesControl.mes == "2026-03-01")
+    tx = Transaccion(
+        fecha="2026-03-15",
+        descripcion="EGRESO TEST",
+        valor=Decimal("10000"),
+        tipo_flujo=TipoFlujo.EGRESO,
+        rubro_id=rubro.id,
+        mes_id=mc.id,
+        banco=Banco.MANUAL,
+        id_banco="MAN-TEST0000000000000000000001",
+    )
+    await tx.insert()
+    return tx
+
+
+async def _referencia_linea(rubro: Rubro) -> PresupuestoLinea:
+    mc = await MesControl.find_one(MesControl.mes == "2026-03-01")
+    ln = PresupuestoLinea(
+        mes_id=mc.id,
+        rubro_id=rubro.id,
+        monto_sugerido=Decimal("100"),
+        prom_3m=Decimal("100"),
+        tendencia_mes=Decimal("0"),
+        crec_pct=Decimal("0"),
+        historia_incompleta=True,
+    )
+    await ln.insert()
+    return ln
+
+
+# ────────────────────────────── GET ──────────────────────────────
+
+
+async def test_get_lista_ordenada(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.get("/api/v1/rubros", headers=h)
+    assert r.status_code == 200
+    d = r.json()
+    assert [x["nombre"] for x in d if x["grupo"] == "operacion"] == [
+        "Arriendos",
+        "Cafetería",
+    ]
+    campos = {"id", "grupo", "nombre", "tipo_flujo", "orden", "activo", "es_sistema"}
+    assert campos <= set(d[0].keys())
+
+
+async def test_get_filtra_por_grupo_y_activo(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.get("/api/v1/rubros?grupo=operacion", headers=h)
+    assert {x["grupo"] for x in r.json()} == {"operacion"}
+    arr = await _rubro("Arriendos")
+    arr.activo = False
+    await arr.save()
+    r = await ac.get("/api/v1/rubros?activo=true", headers=h)
+    assert "Arriendos" not in [x["nombre"] for x in r.json()]
+    r = await ac.get("/api/v1/rubros?activo=false", headers=h)
+    assert [x["nombre"] for x in r.json()] == ["Arriendos"]
+
+
+async def test_get_grupo_invalido_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.get("/api/v1/rubros?grupo=inventado", headers=h)
+    assert r.status_code == 422
+
+
+@pytest.mark.parametrize(
+    "email",
+    [
+        "consulta@roddos.com",
+        "fin@roddos.com",
+        "dir@roddos.com",
+        "admin@roddos.com",
+    ],
+)
+async def test_get_200_los_cuatro_roles(api, email):
+    ac, _ = api
+    h = await _token(ac, email)
+    assert (await ac.get("/api/v1/rubros", headers=h)).status_code == 200
+
+
+# ────────────────────────────── POST (crear) ──────────────────────────────
+
+
+async def test_post_crea_con_orden_max_grupo_mas_1_y_emite_creado(api):
+    ac, c = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/rubros",
+        json={"grupo": "operacion", "nombre": "Freelance", "tipo_flujo": "egreso"},
+        headers=h,
+    )
+    assert r.status_code == 201
+    d = r.json()
+    assert d["orden"] == 3  # máx(operacion)=2 → 3
+    assert d["activo"] is True and d["es_sistema"] is False
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "rubro.creado"})
+    assert ev is not None
+    assert ev["entidad_id"] == d["id"]
+    assert ev["metadata"]["nombre"] == "Freelance"
+
+
+async def test_post_grupo_vacio_arranca_en_1(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/rubros",
+        json={"grupo": "nomina", "nombre": "Sueldos", "tipo_flujo": "egreso"},
+        headers=h,
+    )
+    assert r.status_code == 201
+    assert r.json()["orden"] == 1
+
+
+async def test_post_duplicado_409(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/rubros",
+        json={"grupo": "operacion", "nombre": "Arriendos", "tipo_flujo": "egreso"},
+        headers=h,
+    )
+    assert r.status_code == 409
+
+
+async def test_post_mismo_nombre_en_otro_grupo_ok(api):
+    # El índice es (grupo, nombre): 'Arriendos' puede existir en otro grupo.
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/rubros",
+        json={"grupo": "otros", "nombre": "Arriendos", "tipo_flujo": "egreso"},
+        headers=h,
+    )
+    assert r.status_code == 201
+
+
+async def test_post_grupo_invalido_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/rubros",
+        json={"grupo": "inventado", "nombre": "X", "tipo_flujo": "egreso"},
+        headers=h,
+    )
+    assert r.status_code == 422
+
+
+# ────────────────────────────── PATCH (editar) ──────────────────────────────
+
+
+async def test_patch_nombre_orden_emite_editado_con_cambios(api):
+    ac, c = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    r = await ac.patch(
+        f"/api/v1/rubros/{arr.id}",
+        json={"nombre": "Arriendos sede", "orden": 7},
+        headers=h,
+    )
+    assert r.status_code == 200
+    assert r.json()["nombre"] == "Arriendos sede"
+    assert r.json()["orden"] == 7
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "rubro.editado"})
+    assert ev is not None
+    assert ev["metadata"]["cambios"]["nombre"] == {
+        "anterior": "Arriendos",
+        "nuevo": "Arriendos sede",
+    }
+    assert ev["metadata"]["cambios"]["orden"] == {"anterior": 1, "nuevo": 7}
+
+
+async def test_patch_nombre_duplicado_409(api):
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    r = await ac.patch(
+        f"/api/v1/rubros/{arr.id}", json={"nombre": "Cafetería"}, headers=h
+    )
+    assert r.status_code == 409
+
+
+async def test_patch_sin_cambios_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    r = await ac.patch(f"/api/v1/rubros/{arr.id}", json={}, headers=h)
+    assert r.status_code == 422
+    # Mismo valor actual → tampoco hay cambio efectivo.
+    r = await ac.patch(
+        f"/api/v1/rubros/{arr.id}", json={"nombre": "Arriendos"}, headers=h
+    )
+    assert r.status_code == 422
+
+
+async def test_patch_404_y_id_invalido_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.patch(
+        "/api/v1/rubros/64b000000000000000000000", json={"orden": 9}, headers=h
+    )
+    assert r.status_code == 404
+    r = await ac.patch("/api/v1/rubros/no-es-oid", json={"orden": 9}, headers=h)
+    assert r.status_code == 422
+
+
+# ── D1/B-1: tipo_flujo congelado con referencias ──
+
+
+async def test_patch_tipo_flujo_con_transaccion_409(api):
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    await _referencia_tx(arr)
+    r = await ac.patch(
+        f"/api/v1/rubros/{arr.id}", json={"tipo_flujo": "ingreso"}, headers=h
+    )
+    assert r.status_code == 409
+
+
+async def test_patch_tipo_flujo_con_linea_presupuesto_409(api):
+    # B-1: la guarda es "tiene referencias", no solo "tiene transacciones".
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    await _referencia_linea(arr)
+    r = await ac.patch(
+        f"/api/v1/rubros/{arr.id}", json={"tipo_flujo": "ingreso"}, headers=h
+    )
+    assert r.status_code == 409
+
+
+async def test_patch_tipo_flujo_sin_referencias_200(api):
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    r = await ac.patch(
+        f"/api/v1/rubros/{arr.id}", json={"tipo_flujo": "ingreso"}, headers=h
+    )
+    assert r.status_code == 200
+    assert r.json()["tipo_flujo"] == "ingreso"
+
+
+async def test_patch_nombre_editable_aun_con_referencias(api):
+    # B-1: nombre/orden editables SIEMPRE (no afectan cómputo).
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    await _referencia_tx(arr)
+    r = await ac.patch(
+        f"/api/v1/rubros/{arr.id}", json={"nombre": "Arriendos sede"}, headers=h
+    )
+    assert r.status_code == 200
+
+
+# ────────────────────── Sistema inmutable (parametrizado) ──────────────────────
+
+
+@pytest.mark.parametrize("nombre", SISTEMA)
+async def test_patch_sistema_409(api, nombre):
+    ac, _ = api
+    h = await _token(ac)
+    r = await _rubro(nombre)
+    resp = await ac.patch(f"/api/v1/rubros/{r.id}", json={"orden": 50}, headers=h)
+    assert resp.status_code == 409
+
+
+@pytest.mark.parametrize("nombre", SISTEMA)
+async def test_desactivar_sistema_409(api, nombre):
+    ac, _ = api
+    h = await _token(ac)
+    r = await _rubro(nombre)
+    resp = await ac.post(f"/api/v1/rubros/{r.id}/desactivar", headers=h)
+    assert resp.status_code == 409
+    assert (await _rubro(nombre)).activo is True
+
+
+# ────────────────────────────── Desactivar / reactivar ──────────────────────────────
+
+
+async def test_desactivar_ok_emite_desactivado(api):
+    ac, c = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    r = await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
+    assert r.status_code == 200
+    assert r.json()["activo"] is False
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "rubro.desactivado"})
+    assert ev is not None
+    assert ev["entidad_id"] == str(arr.id)
+
+
+async def test_desactivar_con_movimientos_200_historico_intacto(api):
+    # D2: baja lógica; las transacciones permanecen en la categoría inactiva.
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    tx = await _referencia_tx(arr)
+    r = await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
+    assert r.status_code == 200
+    tx_despues = await Transaccion.get(tx.id)
+    assert tx_despues is not None
+    assert tx_despues.rubro_id == arr.id  # histórico intacto (regla 4)
+
+
+async def test_desactivar_ya_inactivo_409(api):
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
+    r = await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
+    assert r.status_code == 409
+
+
+async def test_reactivar_por_patch_activo_true_emite_editado(api):
+    # B-3: reactivación = PATCH activo:true → rubro.editado {activo false→true};
+    # sin un 34.º evento (CR-S4 queda en +2).
+    ac, c = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
+    r = await ac.patch(f"/api/v1/rubros/{arr.id}", json={"activo": True}, headers=h)
+    assert r.status_code == 200
+    assert r.json()["activo"] is True
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "rubro.editado"})
+    assert ev is not None
+    assert ev["metadata"]["cambios"]["activo"] == {"anterior": False, "nuevo": True}
+
+
+async def test_patch_activo_false_422_usa_desactivar(api):
+    # B-3: la baja va por POST /desactivar (evento rubro.desactivado propio).
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+    r = await ac.patch(f"/api/v1/rubros/{arr.id}", json={"activo": False}, headers=h)
+    assert r.status_code == 422
+
+
+# ────────────────────────────── RBAC exacto ──────────────────────────────
+
+
+@pytest.mark.parametrize("email", ["consulta@roddos.com", "dir@roddos.com"])
+async def test_mutaciones_403_consulta_y_directivo(api, email):
+    ac, _ = api
+    h = await _token(ac, email)
+    arr = await _rubro("Arriendos")
+    body = {"grupo": "otros", "nombre": "Nuevo", "tipo_flujo": "egreso"}
+    assert (await ac.post("/api/v1/rubros", json=body, headers=h)).status_code == 403
+    assert (
+        await ac.patch(f"/api/v1/rubros/{arr.id}", json={"orden": 9}, headers=h)
+    ).status_code == 403
+    assert (
+        await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
+    ).status_code == 403
+
+
+@pytest.mark.parametrize("email", ["fin@roddos.com", "admin@roddos.com"])
+async def test_mutaciones_ok_financiero_y_admin(api, email):
+    ac, _ = api
+    h = await _token(ac, email)
+    body = {"grupo": "otros", "nombre": f"Nuevo {email}", "tipo_flujo": "egreso"}
+    assert (await ac.post("/api/v1/rubros", json=body, headers=h)).status_code == 201
+
+
+# ────────────────────────────── B-5: fail-closed O1 ──────────────────────────────
+
+
+# El transport ASGI de httpx RE-LANZA las excepciones no manejadas de la app
+# (raise_app_exceptions=True); en producción Starlette las convierte en 500.
+# Lo que fija el test es la COMPENSACIÓN (B-5), no el status.
+
+
+async def test_fail_closed_crear_compensa(api, monkeypatch):
+    # B-5: si el emit de rubro.creado falla, el rubro creado se BORRA (compensación).
+    ac, _ = api
+    h = await _token(ac)
+
+    async def _boom(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr("app.rubros.service.emit_audit", _boom)
+    with pytest.raises(RuntimeError):
+        await ac.post(
+            "/api/v1/rubros",
+            json={"grupo": "otros", "nombre": "Fantasma", "tipo_flujo": "egreso"},
+            headers=h,
+        )
+    assert await Rubro.find_one(Rubro.nombre == "Fantasma") is None
+
+
+async def test_fail_closed_editar_compensa(api, monkeypatch):
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+
+    async def _boom(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr("app.rubros.service.emit_audit", _boom)
+    with pytest.raises(RuntimeError):
+        await ac.patch(
+            f"/api/v1/rubros/{arr.id}", json={"nombre": "Efímero"}, headers=h
+        )
+    assert (await Rubro.get(arr.id)).nombre == "Arriendos"  # revertido
+
+
+async def test_fail_closed_desactivar_compensa(api, monkeypatch):
+    ac, _ = api
+    h = await _token(ac)
+    arr = await _rubro("Arriendos")
+
+    async def _boom(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr("app.rubros.service.emit_audit", _boom)
+    with pytest.raises(RuntimeError):
+        await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
+    assert (await Rubro.get(arr.id)).activo is True  # revertido
diff --git a/backend/tests/test_transacciones_manual.py b/backend/tests/test_transacciones_manual.py
index 1496075..f1da3f7 100644
--- a/backend/tests/test_transacciones_manual.py
+++ b/backend/tests/test_transacciones_manual.py
@@ -247,3 +247,16 @@ async def test_rubro_incoherente_con_tipo_422(api):
     recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo")
     r = await _post(ac, h, _body(tipo_flujo="egreso", rubro_id=str(recaudo.id)))
     assert r.status_code == 422
+
+
+async def test_clasificar_hacia_rubro_inactivo_422(api):
+    # B-2a (Kimi PLAN-I C1): la baja lógica impide clasificaciones NUEVAS hacia el
+    # rubro inactivo — la guarda vive aquí (crear_transaccion_manual) y aplicará
+    # igual a la futura auto-clasificación (C3).
+    ac, _ = api
+    h = await _token(ac)
+    inactivo = await Rubro(
+        grupo="operacion", nombre="Renting", orden=50, activo=False
+    ).insert()
+    r = await _post(ac, h, _body(rubro_id=str(inactivo.id)))
+    assert r.status_code == 422
diff --git a/migrations/20260722_reseed_rubros_reales.py b/migrations/20260722_reseed_rubros_reales.py
new file mode 100644
index 0000000..1d73f59
--- /dev/null
+++ b/migrations/20260722_reseed_rubros_reales.py
@@ -0,0 +1,61 @@
+#!/usr/bin/env python
+"""Migración idempotente: re-seed de la taxonomía REAL de categorías (C1, CR-S4).
+
+GO Kimi PLAN-I 9.2 (sprint4-categorias). Alinea la semilla de rubros a las 31
+categorías reales de `docs/modelo/MODELO.md` ('Base real egresos') + 3 de sistema.
+$setOnInsert por (grupo, nombre): re-correr no duplica ni pisa ediciones.
+
+B-4 (Kimi): imprime el REPORTE DE COLISIONES — las llaves donde el seed omitió por
+doc preexistente, con el doc existente vs lo que la semilla habría puesto. El
+operador verifica los coincidentes (D3: las categorías viejas que no estén en la
+taxonomía real quedan activas; el CEO las depura desde la app).
+
+Uso:  python migrations/20260722_reseed_rubros_reales.py "<MONGODB_URI>" [db=compas]
+"""
+
+from __future__ import annotations
+
+import asyncio
+import sys
+
+sys.path.insert(0, "backend")
+
+from app.db import mongo  # noqa: E402
+from app.domain.seed import seed_rubros_reporte  # noqa: E402
+
+
+async def _run(uri: str, db_name: str) -> None:
+    client = mongo.create_client(uri)
+    await mongo.init_beanie_for(client, db_name)
+    insertados, colisiones = await seed_rubros_reporte(client[db_name])
+    print(f"[rubros] {insertados} nuevos insertados (idempotente).")
+    if colisiones:
+        print(f"[rubros] {len(colisiones)} colisiones (doc preexistente, NO tocado):")
+        for c in colisiones:
+            ex, se = c["existente"], c["semilla"]
+            difs = [
+                f"{campo}: existente={ex.get(campo)!r} vs semilla={se[campo]!r}"
+                for campo in ("tipo_flujo", "orden", "activo", "es_sistema")
+                if ex is not None and ex.get(campo) != se[campo]
+            ]
+            marca = " ⚠ DIFIERE → verificar" if difs else " (igual a la semilla)"
+            print(f"  - ({c['grupo']}, {c['nombre']}){marca}")
+            for d in difs:
+                print(f"      {d}")
+    else:
+        print("[rubros] sin colisiones.")
+    client.close()
+
+
+def main() -> None:
+    if len(sys.argv) < 2:
+        sys.exit(
+            'Uso: python migrations/20260722_reseed_rubros_reales.py "<MONGODB_URI>" [db]'
+        )
+    uri = sys.argv[1]
+    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
+    asyncio.run(_run(uri, db_name))
+
+
+if __name__ == "__main__":
+    main()

```
