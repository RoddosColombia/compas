# EVIDENCIA — sprint5-autoclasificacion · I-PR1: C3 auto-clasificación

**PR:** #25 `feat/c3-clasificacion` → `main` · commits `e08f252` + `823c343` (fix test F-02) · 2026-07-22

## 1. Salidas de tests (reales, locales)

### Suite completa del backend
```
412 passed, 40 skipped, 2850 warnings in 245.51s (0:04:05)
```
(40 skipped = requires_real_mongo → job backend-real-mongo del CI. Nota transparente: el
run inicial del CI real-mongo FALLÓ en test_carga_recorrida_identica — el test creaba dos
archivos con contenido idéntico y F-02 correctamente rechaza el mismo hash; el test se
corrigió para probar el solape con archivo distinto (823c343). El run final del PR #25
queda verde y visible en el PR.)

### Tests de C3 (reglas + clasificar + dominio + catálogo + RBAC + semilla)
```
77 passed, 946 warnings in 47.81s
```

### Lint/format
```
ruff check .   → All checks passed!
ruff format --check . → limpio
```

### CI del PR #25
gitleaks ✅ · pip-audit ✅ · runtime-imports ✅ · frontend ✅ · backend + **backend-real-mongo**
(clasificación en carga real: match / sin-match / D2 skip+report / partición por tipo /
re-corrida idéntica / índice único PARCIAL de patrón activo) — estado final visible en el PR.

## 2. Diff completo del código (backend/app, backend/tests, migrations)

```diff
diff --git a/backend/app/api/v1/__init__.py b/backend/app/api/v1/__init__.py
index 5288902..d7f0577 100644
--- a/backend/app/api/v1/__init__.py
+++ b/backend/app/api/v1/__init__.py
@@ -10,6 +10,7 @@ from app.ciclo.router import router as ciclo_router
 from app.cierre.router import router as cierre_router
 from app.control.router import router as control_router
 from app.presupuesto.router import router as presupuesto_router
+from app.reglas.router import router as reglas_router
 from app.rubros.router import router as rubros_router
 from app.transacciones.router import router as transacciones_router
 
@@ -21,5 +22,6 @@ api_router.include_router(ciclo_router)
 api_router.include_router(cierre_router)
 api_router.include_router(control_router)
 api_router.include_router(presupuesto_router)
+api_router.include_router(reglas_router)
 api_router.include_router(rubros_router)
 api_router.include_router(transacciones_router)
diff --git a/backend/app/audit/events.py b/backend/app/audit/events.py
index 29e6a84..93773c0 100644
--- a/backend/app/audit/events.py
+++ b/backend/app/audit/events.py
@@ -6,7 +6,10 @@ CR-S2 / CR-S4).
 + `transaccion.creada` (CR-S2 — Kimi M-1 sprint2-cargas: rastro forense permanente
 del POST manual, la única vía de dinero sin archivo de banco)
 + `rubro.creado`/`rubro.editado` (CR-S4 — C1 categorías administrables, GO Kimi
-PLAN-I 9.2; `rubro.desactivado` ya venía en v1.0, por eso CR-S4 es +2) = 33.
+PLAN-I 9.2; `rubro.desactivado` ya venía en v1.0, por eso CR-S4 es +2)
++ `regla.creada`/`regla.editada`/`regla.desactivada` (CR-S5 — C3
+auto-clasificación, GO Kimi PLAN-I 9.3; la aprobación de aprendidas emite
+`regla.editada` {activa: false→true, via: 'aprobacion'} — sin evento extra) = 36.
 NO se inventan eventos sin CR. El nombre del miembro usa `_`; el valor usa
 `<dominio>.<acción>`."""
 
@@ -55,10 +58,15 @@ class AuditEvento(StrEnum):
     # ── CR-S2 (1) ──
     transaccion_creada = "transaccion.creada"
 
-    # ── CR-S4 (2) → total 33 (C1 categorías administrables) ──
+    # ── CR-S4 (2) — C1 categorías administrables ──
     rubro_creado = "rubro.creado"
     rubro_editado = "rubro.editado"
 
+    # ── CR-S5 (3) → total 36 (C3 auto-clasificación) ──
+    regla_creada = "regla.creada"
+    regla_editada = "regla.editada"
+    regla_desactivada = "regla.desactivada"
 
-# Conjunto de los 33 valores canónicos (para validación/tests de completitud).
+
+# Conjunto de los 36 valores canónicos (para validación/tests de completitud).
 CATALOGO_EVENTOS: frozenset[str] = frozenset(e.value for e in AuditEvento)
diff --git a/backend/app/auth/permissions.py b/backend/app/auth/permissions.py
index 6de219c..5cc7403 100644
--- a/backend/app/auth/permissions.py
+++ b/backend/app/auth/permissions.py
@@ -24,6 +24,8 @@ PERMISSIONS: dict[str, frozenset[Role]] = {
     "capacidad_pago:ver": frozenset({Role.financiero, Role.directivo, Role.admin}),
     # ── CR-S4 (C1 categorías administrables, GO Kimi PLAN-I 9.2) ──
     "rubros:gestionar": frozenset({Role.financiero, Role.admin}),
+    # ── CR-S5 (C3 auto-clasificación, GO Kimi PLAN-I 9.3) ──
+    "reglas:gestionar": frozenset({Role.financiero, Role.admin}),
     # ── Spec §2.4 (autoridad del ciclo mensual — manda sobre §4.1) ──
     "ciclo:abrir": frozenset({Role.financiero, Role.directivo, Role.admin}),
     "ciclo:proponer": frozenset({Role.financiero, Role.directivo, Role.admin}),
diff --git a/backend/app/cargas/mapper.py b/backend/app/cargas/mapper.py
index 33f25c8..55c24ad 100644
--- a/backend/app/cargas/mapper.py
+++ b/backend/app/cargas/mapper.py
@@ -26,9 +26,13 @@ def movimiento_a_transaccion(
     mes_id: PydanticObjectId,
     carga_id: PydanticObjectId | None = None,
     ocurrencia: int = 1,
+    regla_id: PydanticObjectId | None = None,
 ) -> Transaccion:
-    """Construye una Transaccion 'Por clasificar' a partir de un movimiento parseado.
+    """Construye una Transaccion a partir de un movimiento parseado.
 
+    C3: el servicio de carga resuelve el rubro por reglas de clasificación —
+    `rubro_id` llega ya decidido y `regla_id` es el rastro forense (§1.5/F-05) de
+    la regla que clasificó; sin match, rubro='Por clasificar' y regla_id=None.
     `ocurrencia` es el ordinal de la huella dentro del archivo (Kimi A-01): lo asigna
     el servicio de carga contando repeticiones por (fecha, tipo, desc, monto)."""
     fecha = mov.fecha.isoformat()  # date → 'YYYY-MM-DD'
@@ -58,4 +62,5 @@ def movimiento_a_transaccion(
         valor_original=valor_original,
         tasa_cambio=mov.tasa_cambio,
         carga_id=carga_id,
+        regla_id=regla_id,
     )
diff --git a/backend/app/cargas/service.py b/backend/app/cargas/service.py
index 01d7130..282a426 100644
--- a/backend/app/cargas/service.py
+++ b/backend/app/cargas/service.py
@@ -32,12 +32,17 @@ from beanie.operators import In
 
 from app.audit.events import AuditEvento
 from app.audit.service import emit_audit
-from app.cargas.mapper import movimiento_a_transaccion
+from app.cargas.mapper import _TIPO_A_FLUJO, movimiento_a_transaccion
 from app.domain.bancos import Banco
 from app.domain.carga import CargaBancaria, ErrorCarga, EstadoCarga
 from app.domain.mes_control import MesControl
 from app.domain.rubro import Rubro
 from app.domain.transaccion import Transaccion
+from app.reglas.service import (
+    elegir_regla,
+    reglas_activas_por_tipo,
+    rubros_activos_ids,
+)
 
 RUBRO_POR_CLASIFICAR = "Por clasificar"
 
@@ -79,12 +84,18 @@ def _parse(archivo_path: str, banco: Banco):
     return parse_extracto(archivo_path, banco)
 
 
-def _finalizar_carga_doc(carga, resultado, errores, nuevas, duplicadas) -> None:
+def _finalizar_carga_doc(
+    carga, resultado, errores, nuevas, duplicadas, nuevos_docs=()
+) -> None:
     carga.total_filas = len(resultado.movimientos) + len(resultado.errores)
     carga.nuevas = nuevas
     carga.duplicadas = duplicadas
     carga.errores = len(errores)
     carga.errores_detalle = errores
+    # C3 (D3): agregado de clasificación sobre las NUEVAS insertadas — el rastro
+    # por documento es regla_id.
+    carga.clasificadas = sum(1 for d in nuevos_docs if d.regla_id is not None)
+    carga.por_clasificar = len(nuevos_docs) - carga.clasificadas
     carga.estado = EstadoCarga.COMPLETADA
 
 
@@ -152,6 +163,18 @@ async def procesar_carga(
             for e in resultado.errores
         ]
 
+        # C3 (GO Kimi 9.3): reglas activas particionadas por tipo (D1-ii) +
+        # rubros activos, UNA vez por carga. D2: las reglas cuyo rubro esté
+        # inactivo se saltan al clasificar y se reportan (fail-loud B-4).
+        por_tipo = await reglas_activas_por_tipo()
+        activos = await rubros_activos_ids()
+        carga.reglas_con_rubro_inactivo = sorted(
+            r.patron
+            for reglas in por_tipo.values()
+            for r in reglas
+            if r.rubro_id not in activos
+        )
+
         docs: list[Transaccion] = []
         mes_cache: dict[str, object] = {}  # M-03: 1 lookup por mes, no por fila
         conteo: dict[tuple, int] = {}  # A-01: ordinal de ocurrencia por huella
@@ -170,13 +193,19 @@ async def procesar_carga(
                 continue
             clave = _clave_ocurrencia(mov)
             conteo[clave] = conteo.get(clave, 0) + 1
+            # C3: primera regla que matchea (prioridad asc, _id) clasifica;
+            # sin match → 'Por clasificar' (regla 7: jamás se adivina).
+            regla = elegir_regla(
+                mov.descripcion, por_tipo[_TIPO_A_FLUJO[mov.tipo]], activos
+            )
             docs.append(
                 movimiento_a_transaccion(
                     mov,
-                    rubro_id=rubro.id,
+                    rubro_id=regla.rubro_id if regla is not None else rubro.id,
                     mes_id=mc.id,
                     carga_id=carga.id,
                     ocurrencia=conteo[clave],
+                    regla_id=regla.id if regla is not None else None,
                 )
             )
 
@@ -201,7 +230,12 @@ async def procesar_carga(
                 holder["nuevas"] = len(nuevos)
                 holder["duplicadas"] = len(docs) - len(nuevos)
                 _finalizar_carga_doc(
-                    carga, resultado, errores, holder["nuevas"], holder["duplicadas"]
+                    carga,
+                    resultado,
+                    errores,
+                    holder["nuevas"],
+                    holder["duplicadas"],
+                    nuevos_docs=nuevos,
                 )
                 await carga.save(session=session)
 
@@ -221,6 +255,10 @@ async def procesar_carga(
                 "nuevas": holder["nuevas"],
                 "duplicadas": holder["duplicadas"],
                 "errores": len(errores),
+                # C3 (D3): ancla agregada de la clasificación automática.
+                "clasificadas": carga.clasificadas,
+                "por_clasificar": carga.por_clasificar,
+                "reglas_con_rubro_inactivo": carga.reglas_con_rubro_inactivo,
             },
         )
         return carga
diff --git a/backend/app/domain/__init__.py b/backend/app/domain/__init__.py
index 9e40c59..2439eaf 100644
--- a/backend/app/domain/__init__.py
+++ b/backend/app/domain/__init__.py
@@ -12,6 +12,7 @@ from app.domain.configuracion import Configuracion
 from app.domain.idempotency import IdempotencyKey
 from app.domain.mes_control import MesControl
 from app.domain.presupuesto import PresupuestoLinea
+from app.domain.regla_clasificacion import ReglaClasificacion
 from app.domain.rubro import Rubro
 from app.domain.transaccion import Transaccion
 
@@ -23,6 +24,7 @@ DOMAIN_DOCUMENTS: list[type] = [
     CargaBancaria,
     IdempotencyKey,
     PresupuestoLinea,
+    ReglaClasificacion,
 ]
 
 __all__ = [
@@ -33,5 +35,6 @@ __all__ = [
     "CargaBancaria",
     "IdempotencyKey",
     "PresupuestoLinea",
+    "ReglaClasificacion",
     "DOMAIN_DOCUMENTS",
 ]
diff --git a/backend/app/domain/carga.py b/backend/app/domain/carga.py
index 5ba5f79..1bbdef3 100644
--- a/backend/app/domain/carga.py
+++ b/backend/app/domain/carga.py
@@ -54,6 +54,14 @@ class CargaBancaria(Document):
     nuevas: int = 0
     duplicadas: int = 0
     errores: int = 0
+    # C3 (GO Kimi 9.3): contadores de auto-clasificación sobre las NUEVAS
+    # insertadas (D3: el rastro por doc es regla_id; el agregado vive aquí y en
+    # la metadata de carga.completada).
+    clasificadas: int = 0
+    por_clasificar: int = 0
+    # D2 (fail-loud informativo, patrón B-4): patrones de reglas ACTIVAS cuyo
+    # rubro está inactivo — se saltaron al clasificar esta carga.
+    reglas_con_rubro_inactivo: list[str] = Field(default_factory=list)
     errores_detalle: list[ErrorCarga] = Field(default_factory=list)
     estado: EstadoCarga = EstadoCarga.PROCESANDO
     motivo_fallo: str | None = None
diff --git a/backend/app/domain/regla_clasificacion.py b/backend/app/domain/regla_clasificacion.py
new file mode 100644
index 0000000..d812a95
--- /dev/null
+++ b/backend/app/domain/regla_clasificacion.py
@@ -0,0 +1,106 @@
+# backend/app/domain/regla_clasificacion.py
+"""ReglaClasificacion (Spec §1.9, C3 auto-clasificación — GO Kimi PLAN-I 9.3).
+
+Regla administrable: `patron` (contains case-insensitive y sin tildes) sobre la
+descripción del movimiento → `rubro_id`. "Primera regla que matchea por prioridad
+gana" (ascendente; empate → _id como desempate estable). `origen`:
+manual | aprendida (propuesta desde reclasificación con `proponer_regla`; requiere
+aprobación del Financiero, NUNCA auto-activada — §1.9).
+
+NORMALIZACIÓN ÚNICA COMPARTIDA (Kimi §3 — el punto delicado): `normalizar_texto`
+es LA función que normaliza tanto el patrón al escribir la regla
+(`patron_normalizado`, derivado automáticamente) como la descripción al matchear
+(`coincide`). Si divergieran, habría fallo silencioso — por eso viven juntas aquí.
+
+Unicidad (regla 7): índice único PARCIAL (patron_normalizado, tipo_flujo) con
+`activa=true` — dos reglas ACTIVAS idénticas son ambigüedad; duplicados
+desactivados se permiten (histórico de configuración).
+"""
+
+import unicodedata
+from datetime import datetime
+from enum import StrEnum
+
+from beanie import Document, PydanticObjectId
+from pydantic import ConfigDict, Field, field_validator, model_validator
+from pymongo import IndexModel
+
+from app.core.time import now_utc
+from app.domain.rubro import TipoFlujo
+
+REGLAS_COLLECTION = "reglas_clasificacion"
+
+PATRON_MIN = 3  # guarda contra match-all (Kimi §3)
+
+
+def normalizar_texto(texto: str) -> str:
+    """lower + sin tildes/diacríticos + trim. ÚNICA normalización del matching."""
+    descompuesto = unicodedata.normalize("NFD", texto)
+    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
+    return sin_tildes.lower().strip()
+
+
+def coincide(patron: str, descripcion: str) -> bool:
+    """¿El patrón (contains normalizado) aparece en la descripción?"""
+    return normalizar_texto(patron) in normalizar_texto(descripcion)
+
+
+class OrigenRegla(StrEnum):
+    MANUAL = "manual"
+    APRENDIDA = "aprendida"  # propuesta; requiere aprobación (§1.9)
+
+
+class ReglaClasificacion(Document):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    patron: str = Field(min_length=PATRON_MIN, max_length=120)
+    patron_normalizado: str = ""  # derivado de patron (model_validator)
+    rubro_id: PydanticObjectId
+    tipo_flujo: TipoFlujo
+    prioridad: int
+    origen: OrigenRegla = OrigenRegla.MANUAL
+    activa: bool = True
+    creada_por: str
+    created_at: datetime = Field(default_factory=now_utc)
+
+    class Settings:
+        name = REGLAS_COLLECTION
+        indexes = [
+            IndexModel([("prioridad", 1)], name="por_prioridad"),
+            # Regla 7: dos reglas ACTIVAS con el mismo patrón+tipo = ambigüedad.
+            # Parcial: las desactivadas no cuentan (mongomock no lo exige → el
+            # pre-check del service cubre el flujo normal; el índice, la carrera).
+            IndexModel(
+                [("patron_normalizado", 1), ("tipo_flujo", 1)],
+                name="patron_tipo_activa_unico",
+                unique=True,
+                partialFilterExpression={"activa": True},
+            ),
+        ]
+
+    @field_validator("tipo_flujo", mode="before")
+    @classmethod
+    def _cast_tipo(cls, v: object) -> object:
+        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)
+
+    @field_validator("origen", mode="before")
+    @classmethod
+    def _cast_origen(cls, v: object) -> object:
+        return v if isinstance(v, OrigenRegla) else OrigenRegla(v)
+
+    @field_validator("created_at")
+    @classmethod
+    def _aware(cls, v: datetime | None) -> datetime | None:
+        if v is not None and v.tzinfo is None:
+            raise ValueError("datetime debe ser UTC-aware (regla 2)")
+        return v
+
+    @model_validator(mode="after")
+    def _derivar_normalizado(self) -> "ReglaClasificacion":
+        # SIEMPRE derivado del patrón vigente — nunca se acepta un valor divergente.
+        object.__setattr__(self, "patron_normalizado", normalizar_texto(self.patron))
+        if len(self.patron_normalizado) < PATRON_MIN:
+            raise ValueError(
+                f"el patrón normalizado queda menor a {PATRON_MIN} caracteres"
+            )
+        return self
diff --git a/backend/app/domain/seed.py b/backend/app/domain/seed.py
index a658f8a..cd4858f 100644
--- a/backend/app/domain/seed.py
+++ b/backend/app/domain/seed.py
@@ -77,3 +77,72 @@ async def seed_configuracion(db: Any) -> int:
         db, CONFIGURACION_COLLECTION, SEMILLA_CONFIGURACION, ["clave", "vigente_desde"]
     )
     return insertados
+
+
+# ── C3: semilla de reglas de clasificación (GO Kimi PLAN-I 9.3) ──────────────
+#
+# SOLO patrones genéricos — NUNCA nombres de personas (Ley 1581, Kimi §3): las
+# genéricas de ingreso 'Abono'/'Recibido de' → 'Recaudo' (PRD M7 / MODELO §C3),
+# prioridad alta. Los patrones de egreso (comercios del mapeo de `Base real
+# egresos`) se cargan desde la app o en una extensión de esta lista cuando el
+# CEO comparta el mapeo (dato real, vive fuera del repo). origen='manual':
+# curaduría, no aprendizaje.
+SEMILLA_REGLAS: list[dict] = [
+    {
+        "patron": "Abono",
+        "tipo_flujo": "ingreso",
+        "rubro_nombre": "Recaudo",
+        "prioridad": 1,
+        "origen": "manual",
+    },
+    {
+        "patron": "Recibido de",
+        "tipo_flujo": "ingreso",
+        "rubro_nombre": "Recaudo",
+        "prioridad": 2,
+        "origen": "manual",
+    },
+]
+
+
+async def seed_reglas_reporte(db: Any) -> tuple[int, list[dict]]:
+    """Siembra las reglas de clasificación (idempotente por
+    (patron_normalizado, tipo_flujo); reporte de colisiones B-4). FAIL-LOUD
+    (Kimi §3): si un rubro destino del mapeo no existe → LookupError, jamás una
+    regla huérfana silenciosa."""
+    from app.domain.regla_clasificacion import (
+        REGLAS_COLLECTION,
+        normalizar_texto,
+    )
+    from app.domain.rubro import RUBROS_COLLECTION
+
+    filas: list[dict] = []
+    for spec in SEMILLA_REGLAS:
+        rubro = await db[RUBROS_COLLECTION].find_one({"nombre": spec["rubro_nombre"]})
+        if rubro is None:
+            raise LookupError(
+                f"semilla de reglas: falta el rubro destino "
+                f"'{spec['rubro_nombre']}' (correr seed_rubros primero)"
+            )
+        filas.append(
+            {
+                "patron": spec["patron"],
+                "patron_normalizado": normalizar_texto(spec["patron"]),
+                "rubro_id": rubro["_id"],
+                "tipo_flujo": spec["tipo_flujo"],
+                "prioridad": spec["prioridad"],
+                "origen": spec["origen"],
+                "activa": True,
+                "creada_por": "semilla",
+                "created_at": _ahora_utc(),
+            }
+        )
+    return await _upsert_muchos(
+        db, REGLAS_COLLECTION, filas, ["patron_normalizado", "tipo_flujo"]
+    )
+
+
+def _ahora_utc():
+    from app.core.time import now_utc
+
+    return now_utc()
diff --git a/backend/app/reglas/__init__.py b/backend/app/reglas/__init__.py
new file mode 100644
index 0000000..b4a5f45
--- /dev/null
+++ b/backend/app/reglas/__init__.py
@@ -0,0 +1 @@
+# backend/app/reglas/__init__.py
diff --git a/backend/app/reglas/router.py b/backend/app/reglas/router.py
new file mode 100644
index 0000000..9c763c1
--- /dev/null
+++ b/backend/app/reglas/router.py
@@ -0,0 +1,156 @@
+# backend/app/reglas/router.py
+"""/api/v1/reglas-clasificacion — C3 auto-clasificación (CR-S5, Spec §319).
+
+MARCADO PARA AUDITORÍA KIMI (gate I-PR1).
+
+RBAC: GET con `dashboard:leer`; mutaciones con `reglas:gestionar` = {financiero,
+admin} (CR-S5) + `verify_origin`. Sin Idempotency-Key (mismo criterio de C1: no es
+movimiento de dinero; el índice único de patrón activo hace inocuo el replay).
+`aplicar-pendientes` es idempotente por construcción (lo clasificado no se toca)."""
+
+from fastapi import APIRouter, Depends, HTTPException, Query
+from pydantic import BaseModel, ConfigDict, Field, field_validator
+
+from app.auth.deps import require_permission
+from app.auth.models import User
+from app.auth.router import verify_origin
+from app.domain.regla_clasificacion import ReglaClasificacion
+from app.domain.rubro import TipoFlujo
+from app.reglas import service
+
+router = APIRouter(prefix="/reglas-clasificacion", tags=["reglas"])
+
+
+class ReglaCrearBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    patron: str = Field(min_length=3, max_length=120)
+    rubro_id: str
+    tipo_flujo: TipoFlujo
+    prioridad: int = 100
+
+    @field_validator("tipo_flujo", mode="before")
+    @classmethod
+    def _cast_tipo(cls, v: object) -> object:
+        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)
+
+
+class ReglaEditarBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    patron: str | None = Field(default=None, min_length=3, max_length=120)
+    prioridad: int | None = None
+    rubro_id: str | None = None
+    activa: bool | None = None  # solo true (reactivar); false → 422
+
+
+def _serializar(r: ReglaClasificacion) -> dict:
+    return {
+        "id": str(r.id),
+        "patron": r.patron,
+        "patron_normalizado": r.patron_normalizado,
+        "rubro_id": str(r.rubro_id),
+        "tipo_flujo": r.tipo_flujo.value,
+        "prioridad": r.prioridad,
+        "origen": r.origen.value,
+        "activa": r.activa,
+        "creada_por": r.creada_por,
+    }
+
+
+def _parse_tipo(tipo: str | None) -> TipoFlujo | None:
+    if tipo is None:
+        return None
+    try:
+        return TipoFlujo(tipo)
+    except ValueError:
+        raise HTTPException(422, f"tipo_flujo inválido: '{tipo}'") from None
+
+
+@router.get("")
+async def listar(
+    activa: bool | None = Query(default=None),
+    tipo_flujo: str | None = Query(default=None),
+    _: User = Depends(require_permission("dashboard:leer")),
+):
+    reglas = await service.listar_reglas(
+        activa=activa, tipo_flujo=_parse_tipo(tipo_flujo)
+    )
+    return [_serializar(r) for r in reglas]
+
+
+@router.post("", status_code=201)
+async def crear(
+    body: ReglaCrearBody,
+    user: User = Depends(require_permission("reglas:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        regla = await service.crear_regla(
+            patron=body.patron,
+            rubro_id=body.rubro_id,
+            tipo_flujo=body.tipo_flujo,
+            prioridad=body.prioridad,
+            usuario_id=user.id,
+        )
+    except service.ReglasError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(regla)
+
+
+@router.patch("/{regla_id}")
+async def editar(
+    regla_id: str,
+    body: ReglaEditarBody,
+    user: User = Depends(require_permission("reglas:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        regla = await service.editar_regla(
+            regla_id=regla_id,
+            usuario_id=user.id,
+            patron=body.patron,
+            prioridad=body.prioridad,
+            rubro_id=body.rubro_id,
+            activa=body.activa,
+        )
+    except service.ReglasError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(regla)
+
+
+@router.post("/{regla_id}/desactivar")
+async def desactivar(
+    regla_id: str,
+    user: User = Depends(require_permission("reglas:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        regla = await service.desactivar_regla(regla_id=regla_id, usuario_id=user.id)
+    except service.ReglasError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(regla)
+
+
+@router.post("/{regla_id}/aprobar")
+async def aprobar(
+    regla_id: str,
+    user: User = Depends(require_permission("reglas:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        regla = await service.aprobar_regla(regla_id=regla_id, usuario_id=user.id)
+    except service.ReglasError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(regla)
+
+
+@router.post("/aplicar-pendientes")
+async def aplicar_pendientes(
+    user: User = Depends(require_permission("reglas:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        return await service.aplicar_pendientes(usuario_id=user.id)
+    except service.ReglasError as e:
+        raise HTTPException(e.status, e.detalle) from e
diff --git a/backend/app/reglas/service.py b/backend/app/reglas/service.py
new file mode 100644
index 0000000..f89e2a0
--- /dev/null
+++ b/backend/app/reglas/service.py
@@ -0,0 +1,444 @@
+# backend/app/reglas/service.py
+"""C3 auto-clasificación (CR-S5, GO Kimi PLAN-I 9.3): reglas administrables.
+
+MARCADO PARA AUDITORÍA KIMI (clasifica movimientos de dinero; gate I-PR1).
+
+Decisiones fijadas en el gate del PLAN:
+  - D1 (coherencia de tipos POR CONSTRUCCIÓN): `_validar_rubro_destino` exige
+    rubro existente (404), activo (422) y con `tipo_flujo` == el de la regla (409)
+    — en crear, editar Y en los dos puntos de activación (aprobar / PATCH
+    activa:true — B-1 Kimi: el rubro pudo desactivarse entre la creación y la
+    activación; el estado "regla activa → rubro inactivo" solo puede existir por
+    desactivación POSTERIOR del rubro, nunca por decisión de activación).
+  - D2 (guarda de inactivos): `elegir_regla` salta reglas cuyo rubro no esté en el
+    set de activos — la fila cae a 'Por clasificar' (regla 7) y el llamador
+    reporta (`reglas_con_rubro_inactivo`, fail-loud informativo patrón B-4).
+    NO hay desactivación en cascada: si el rubro se reactiva, la regla vuelve a
+    operar sola.
+  - Precedencia DETERMINISTA: prioridad ascendente; empate → str(_id) (estable).
+  - D4/B-2: `aplicar_pendientes` re-corre reglas SOLO sobre 'Por clasificar' de
+    meses NO cerrados (regla 4) y SELLA cada doc con clasificada_por +
+    clasificada_at + regla_id — rastro forense completo por documento (quién
+    disparó el lote / cuándo / qué regla), sin evento agregado.
+  - D5 (§1.9): las aprendidas nacen `activa=False` SIEMPRE (forzado en
+    `proponer_regla_aprendida`) y solo se activan por `/aprobar` o PATCH
+    activa:true (misma autoridad `reglas:gestionar`) — nunca una vía automática.
+  - Auditoría FAIL-CLOSED estilo O1 (estándar C1/B-5): mutar → emitir →
+    compensar si el emit falla → propagar.
+"""
+
+from beanie import PydanticObjectId
+from pymongo.errors import DuplicateKeyError
+
+from app.audit.events import AuditEvento
+from app.audit.service import emit_audit
+from app.core.time import now_utc
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.regla_clasificacion import (
+    OrigenRegla,
+    ReglaClasificacion,
+    coincide,
+    normalizar_texto,
+)
+from app.domain.rubro import Rubro, TipoFlujo
+from app.domain.transaccion import Transaccion
+
+RUBRO_POR_CLASIFICAR = "Por clasificar"
+
+
+class ReglasError(Exception):
+    def __init__(self, detalle: str, status: int = 422) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+        self.status = status
+
+
+# ────────────────────────── matching (puro, testeable) ──────────────────────────
+
+
+def elegir_regla(
+    descripcion: str,
+    reglas: list[ReglaClasificacion],
+    rubros_activos: set[PydanticObjectId],
+) -> ReglaClasificacion | None:
+    """Primera regla que matchea por (prioridad asc, _id) — determinista.
+    D2: una regla cuyo rubro no esté activo SE SALTA (el llamador reporta).
+    El llamador ya particionó `reglas` por tipo_flujo (D1-ii)."""
+    for regla in sorted(reglas, key=lambda r: (r.prioridad, str(r.id))):
+        if regla.rubro_id not in rubros_activos:
+            continue
+        if coincide(regla.patron, descripcion):
+            return regla
+    return None
+
+
+async def reglas_activas_por_tipo() -> dict[TipoFlujo, list[ReglaClasificacion]]:
+    """Reglas activas particionadas por tipo_flujo (D1-ii: una regla de ingreso
+    jamás se evalúa contra un egreso)."""
+    out: dict[TipoFlujo, list[ReglaClasificacion]] = {
+        TipoFlujo.EGRESO: [],
+        TipoFlujo.INGRESO: [],
+    }
+    async for regla in ReglaClasificacion.find(ReglaClasificacion.activa == True):  # noqa: E712
+        out[regla.tipo_flujo].append(regla)
+    return out
+
+
+async def rubros_activos_ids() -> set[PydanticObjectId]:
+    ids: set[PydanticObjectId] = set()
+    async for r in Rubro.find(Rubro.activo == True):  # noqa: E712
+        ids.add(r.id)
+    return ids
+
+
+# ────────────────────────────── CRUD ──────────────────────────────
+
+
+async def _obtener(regla_id: str) -> ReglaClasificacion:
+    try:
+        rid = PydanticObjectId(regla_id)
+    except Exception:
+        raise ReglasError("regla_id inválido", 422) from None
+    regla = await ReglaClasificacion.get(rid)
+    if regla is None:
+        raise ReglasError("la regla no existe", 404)
+    return regla
+
+
+async def _validar_rubro_destino(
+    rubro_id: PydanticObjectId, tipo_flujo: TipoFlujo
+) -> Rubro:
+    """D1 + B-1: rubro existente (404), ACTIVO (422) y de tipo coherente (409).
+    Se invoca al crear, al editar el destino y en TODA activación."""
+    rubro = await Rubro.get(rubro_id)
+    if rubro is None:
+        raise ReglasError("el rubro destino no existe", 404)
+    if not rubro.activo:
+        raise ReglasError(f"el rubro '{rubro.nombre}' está inactivo (D1)", 422)
+    if rubro.tipo_flujo is not tipo_flujo:
+        raise ReglasError(
+            f"el rubro '{rubro.nombre}' es {rubro.tipo_flujo.value}, incoherente "
+            f"con una regla de {tipo_flujo.value} (D1)",
+            409,
+        )
+    return rubro
+
+
+async def _patron_activo_duplicado(
+    patron: str, tipo_flujo: TipoFlujo, excepto: PydanticObjectId | None = None
+) -> bool:
+    filtros = [
+        ReglaClasificacion.patron_normalizado == normalizar_texto(patron),
+        ReglaClasificacion.tipo_flujo == tipo_flujo,
+        ReglaClasificacion.activa == True,  # noqa: E712
+    ]
+    existente = await ReglaClasificacion.find(*filtros).first_or_none()
+    return existente is not None and (excepto is None or existente.id != excepto)
+
+
+async def listar_reglas(
+    *, activa: bool | None = None, tipo_flujo: TipoFlujo | None = None
+) -> list[ReglaClasificacion]:
+    filtros = []
+    if activa is not None:
+        filtros.append(ReglaClasificacion.activa == activa)
+    if tipo_flujo is not None:
+        filtros.append(ReglaClasificacion.tipo_flujo == tipo_flujo)
+    return (
+        await ReglaClasificacion.find(*filtros)
+        .sort(+ReglaClasificacion.prioridad)
+        .to_list()
+    )
+
+
+async def crear_regla(
+    *,
+    patron: str,
+    rubro_id: str,
+    tipo_flujo: TipoFlujo,
+    prioridad: int,
+    usuario_id: str,
+) -> ReglaClasificacion:
+    try:
+        rid = PydanticObjectId(rubro_id)
+    except Exception:
+        raise ReglasError("rubro_id inválido", 422) from None
+    rubro = await _validar_rubro_destino(rid, tipo_flujo)
+    if await _patron_activo_duplicado(patron, tipo_flujo):
+        raise ReglasError(
+            f"ya existe una regla ACTIVA con el patrón '{patron}' para "
+            f"{tipo_flujo.value} (regla 7: ambigüedad)",
+            409,
+        )
+    regla = ReglaClasificacion(
+        patron=patron,
+        rubro_id=rid,
+        tipo_flujo=tipo_flujo,
+        prioridad=prioridad,
+        origen=OrigenRegla.MANUAL,
+        creada_por=usuario_id,
+    )
+    try:
+        await regla.insert()
+    except DuplicateKeyError:
+        raise ReglasError(
+            f"ya existe una regla ACTIVA con el patrón '{patron}'", 409
+        ) from None
+    try:
+        await emit_audit(
+            AuditEvento.regla_creada,
+            entidad="regla_clasificacion",
+            entidad_id=str(regla.id),
+            actor_id=usuario_id,
+            metadata={
+                "patron": patron,
+                "tipo_flujo": tipo_flujo.value,
+                "rubro": rubro.nombre,
+                "prioridad": prioridad,
+                "origen": regla.origen.value,
+            },
+        )
+    except Exception:
+        await regla.delete()  # B-5/O1: sin rastro no hay regla
+        raise
+    return regla
+
+
+async def proponer_regla_aprendida(
+    *,
+    patron: str,
+    rubro_id: PydanticObjectId,
+    tipo_flujo: TipoFlujo,
+    usuario_id: str,
+    prioridad: int = 100,
+) -> ReglaClasificacion:
+    """D5 (§1.9): la ÚNICA vía de creación de aprendidas — fuerza activa=False
+    (nunca auto-activada); la activa el Financiero por /aprobar."""
+    rubro = await _validar_rubro_destino(rubro_id, tipo_flujo)
+    if await _patron_activo_duplicado(patron, tipo_flujo):
+        raise ReglasError(f"ya existe una regla ACTIVA con el patrón '{patron}'", 409)
+    regla = ReglaClasificacion(
+        patron=patron,
+        rubro_id=rubro_id,
+        tipo_flujo=tipo_flujo,
+        prioridad=prioridad,
+        origen=OrigenRegla.APRENDIDA,
+        activa=False,  # §1.9: NUNCA auto-activada
+        creada_por=usuario_id,
+    )
+    await regla.insert()
+    try:
+        await emit_audit(
+            AuditEvento.regla_creada,
+            entidad="regla_clasificacion",
+            entidad_id=str(regla.id),
+            actor_id=usuario_id,
+            metadata={
+                "patron": patron,
+                "tipo_flujo": tipo_flujo.value,
+                "rubro": rubro.nombre,
+                "origen": "aprendida",
+                "activa": False,
+            },
+        )
+    except Exception:
+        await regla.delete()
+        raise
+    return regla
+
+
+async def editar_regla(
+    *,
+    regla_id: str,
+    usuario_id: str,
+    patron: str | None = None,
+    prioridad: int | None = None,
+    rubro_id: str | None = None,
+    activa: bool | None = None,
+) -> ReglaClasificacion:
+    regla = await _obtener(regla_id)
+    cambios: dict[str, dict] = {}
+    previos: dict[str, object] = {}
+
+    if activa is not None:
+        if activa is False:
+            raise ReglasError(
+                "la baja va por POST /reglas-clasificacion/{id}/desactivar", 422
+            )
+        if not regla.activa:
+            # B-1 Kimi: la ACTIVACIÓN revalida el destino (pudo desactivarse
+            # el rubro entre la creación y este momento).
+            destino = (
+                PydanticObjectId(rubro_id) if rubro_id is not None else regla.rubro_id
+            )
+            await _validar_rubro_destino_para_activar(destino, regla.tipo_flujo)
+            if await _patron_activo_duplicado(
+                patron if patron is not None else regla.patron,
+                regla.tipo_flujo,
+                excepto=regla.id,
+            ):
+                raise ReglasError("otra regla ACTIVA ya usa ese patrón", 409)
+            previos["activa"] = regla.activa
+            cambios["activa"] = {"anterior": False, "nuevo": True}
+            regla.activa = True
+
+    if rubro_id is not None:
+        try:
+            rid = PydanticObjectId(rubro_id)
+        except Exception:
+            raise ReglasError("rubro_id inválido", 422) from None
+        if rid != regla.rubro_id:
+            await _validar_rubro_destino(rid, regla.tipo_flujo)
+            previos["rubro_id"] = regla.rubro_id
+            cambios["rubro_id"] = {"anterior": str(regla.rubro_id), "nuevo": str(rid)}
+            regla.rubro_id = rid
+
+    if patron is not None and patron != regla.patron:
+        if regla.activa and await _patron_activo_duplicado(
+            patron, regla.tipo_flujo, excepto=regla.id
+        ):
+            raise ReglasError("otra regla ACTIVA ya usa ese patrón", 409)
+        previos["patron"] = regla.patron
+        cambios["patron"] = {"anterior": regla.patron, "nuevo": patron}
+        regla.patron = patron
+
+    if prioridad is not None and prioridad != regla.prioridad:
+        previos["prioridad"] = regla.prioridad
+        cambios["prioridad"] = {"anterior": regla.prioridad, "nuevo": prioridad}
+        regla.prioridad = prioridad
+
+    if not cambios:
+        raise ReglasError("nada que editar (ningún campo cambia)", 422)
+
+    try:
+        await regla.save()
+    except DuplicateKeyError:
+        raise ReglasError("otra regla ACTIVA ya usa ese patrón", 409) from None
+
+    try:
+        await emit_audit(
+            AuditEvento.regla_editada,
+            entidad="regla_clasificacion",
+            entidad_id=str(regla.id),
+            actor_id=usuario_id,
+            metadata={"cambios": cambios},
+        )
+    except Exception:
+        for campo, valor in previos.items():
+            setattr(regla, campo, valor)
+        await regla.save()
+        raise
+    return regla
+
+
+async def _validar_rubro_destino_para_activar(
+    rubro_id: PydanticObjectId, tipo_flujo: TipoFlujo
+) -> Rubro:
+    """B-1: en activación, rubro inactivo/incoherente es 409 (decisión explícita
+    de activar hacia un destino inválido, no un dato mal formado)."""
+    rubro = await Rubro.get(rubro_id)
+    if rubro is None:
+        raise ReglasError("el rubro destino no existe", 404)
+    if not rubro.activo:
+        raise ReglasError(
+            f"no se puede activar: el rubro '{rubro.nombre}' está inactivo (B-1)",
+            409,
+        )
+    if rubro.tipo_flujo is not tipo_flujo:
+        raise ReglasError(
+            f"no se puede activar: el rubro '{rubro.nombre}' es "
+            f"{rubro.tipo_flujo.value} (B-1/D1)",
+            409,
+        )
+    return rubro
+
+
+async def desactivar_regla(*, regla_id: str, usuario_id: str) -> ReglaClasificacion:
+    regla = await _obtener(regla_id)
+    if not regla.activa:
+        raise ReglasError("la regla ya está inactiva", 409)
+    regla.activa = False
+    await regla.save()
+    try:
+        await emit_audit(
+            AuditEvento.regla_desactivada,
+            entidad="regla_clasificacion",
+            entidad_id=str(regla.id),
+            actor_id=usuario_id,
+            metadata={"patron": regla.patron},
+        )
+    except Exception:
+        regla.activa = True
+        await regla.save()
+        raise
+    return regla
+
+
+async def aprobar_regla(*, regla_id: str, usuario_id: str) -> ReglaClasificacion:
+    """§1.9: activa una regla APRENDIDA propuesta. B-1: revalida el destino."""
+    regla = await _obtener(regla_id)
+    if regla.origen is not OrigenRegla.APRENDIDA:
+        raise ReglasError("solo las reglas aprendidas pasan por aprobación", 409)
+    if regla.activa:
+        raise ReglasError("la regla ya está activa", 409)
+    await _validar_rubro_destino_para_activar(regla.rubro_id, regla.tipo_flujo)
+    if await _patron_activo_duplicado(regla.patron, regla.tipo_flujo, excepto=regla.id):
+        raise ReglasError("otra regla ACTIVA ya usa ese patrón", 409)
+
+    regla.activa = True
+    await regla.save()
+    try:
+        await emit_audit(
+            AuditEvento.regla_editada,
+            entidad="regla_clasificacion",
+            entidad_id=str(regla.id),
+            actor_id=usuario_id,
+            metadata={
+                "cambios": {"activa": {"anterior": False, "nuevo": True}},
+                "via": "aprobacion",
+            },
+        )
+    except Exception:
+        regla.activa = False
+        await regla.save()
+        raise
+    return regla
+
+
+# ────────────────────── aplicar-pendientes (D4 + B-2) ──────────────────────
+
+
+async def aplicar_pendientes(*, usuario_id: str) -> dict:
+    """Re-corre las reglas SOLO sobre 'Por clasificar' de meses NO cerrados
+    (regla 4). Idempotente: lo ya clasificado no se toca. B-2: cada doc
+    reclasificado queda SELLADO con clasificada_por/at + regla_id."""
+    pc = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
+    if pc is None:
+        raise ReglasError(
+            "falta el rubro de sistema 'Por clasificar' (correr semillas)", 500
+        )
+    meses_abiertos = [
+        mc.id async for mc in MesControl.find(MesControl.estado != EstadoMes.CERRADO)
+    ]
+    por_tipo = await reglas_activas_por_tipo()
+    activos = await rubros_activos_ids()
+
+    clasificadas = 0
+    sin_match = 0
+    ahora = now_utc()
+    async for tx in Transaccion.find(
+        Transaccion.rubro_id == pc.id,
+        {"mes_id": {"$in": meses_abiertos}},
+    ):
+        regla = elegir_regla(tx.descripcion, por_tipo[tx.tipo_flujo], activos)
+        if regla is None:
+            sin_match += 1
+            continue
+        tx.rubro_id = regla.rubro_id
+        tx.regla_id = regla.id
+        tx.clasificada_por = usuario_id  # B-2: quién disparó el lote
+        tx.clasificada_at = ahora  # B-2: cuándo
+        await tx.save()
+        clasificadas += 1
+
+    return {"clasificadas": clasificadas, "sin_match": sin_match}
diff --git a/backend/app/transacciones/router.py b/backend/app/transacciones/router.py
index 3c0e6b8..cf09cc9 100644
--- a/backend/app/transacciones/router.py
+++ b/backend/app/transacciones/router.py
@@ -1,10 +1,13 @@
 # backend/app/transacciones/router.py
-"""POST /api/v1/transacciones — transacción manual con Idempotency-Key (§1.12).
+"""POST /api/v1/transacciones — transacción manual con Idempotency-Key (§1.12)
++ PATCH /transacciones/{id}/clasificar — reclasificación manual (C3, CR-S5).
 
 MARCADO PARA AUDITORÍA KIMI (flujo crítico).
 
 Regla 1: `valor` viaja como STRING (strict=True rechaza numbers JSON). El replay
-idempotente devuelve la respuesta original; misma key + payload distinto → 422."""
+idempotente devuelve la respuesta original; misma key + payload distinto → 422.
+La reclasificación NO lleva Idempotency-Key: es idempotente por naturaleza
+(re-aplicar el mismo rubro no cambia nada) y no crea dinero."""
 
 import hashlib
 import json
@@ -134,3 +137,31 @@ async def crear_manual(
     marca.response_body = respuesta
     await marca.save()
     return respuesta
+
+
+class ClasificarBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    rubro_id: str
+    proponer_regla: bool = False  # §1.9/D5: crea propuesta APRENDIDA inactiva
+    patron: str | None = Field(default=None, min_length=3, max_length=120)
+
+
+@router.patch("/{transaccion_id}/clasificar")
+async def clasificar(
+    transaccion_id: str,
+    body: ClasificarBody,
+    user: User = Depends(require_permission("cargas:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        tx = await service.reclasificar_transaccion(
+            tx_id=transaccion_id,
+            rubro_id=body.rubro_id,
+            usuario_id=user.id,
+            proponer_regla=body.proponer_regla,
+            patron=body.patron,
+        )
+    except service.TransaccionManualError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(tx)
diff --git a/backend/app/transacciones/service.py b/backend/app/transacciones/service.py
index ac1f51f..3a5ebff 100644
--- a/backend/app/transacciones/service.py
+++ b/backend/app/transacciones/service.py
@@ -9,7 +9,16 @@ las tardías llegan con el flujo de cierre, Sprint 4); rubro explícito debe exi
 estar activo y ser coherente con tipo_flujo (regla 7: no se adivina); sin rubro →
 'Por clasificar'. Eventos: `transaccion.creada` en TODA creación manual (CR-S2,
 Kimi M-1 — rastro forense permanente) + `transaccion.clasificada` si además el
-usuario clasificó (rubro explícito)."""
+usuario clasificó (rubro explícito).
+
+C3 (GO Kimi PLAN-I 9.3) — `reclasificar_transaccion`: mueve una transacción a un
+rubro existente + ACTIVO (422) + de tipo coherente (409, D1); mes cerrado → 409
+(regla 4: el histórico congelado no se reclasifica). Solo mutan rubro_id/
+clasificada_por/at — fecha, valor, banco, id_banco INMUTABLES (Spec §2.2). Emite
+`transaccion.clasificada` {rubro_anterior→rubro_nuevo} FAIL-CLOSED (compensa si el
+emit falla). Con `proponer_regla` (+patrón), crea una ReglaClasificacion APRENDIDA
+inactiva (§1.9: nunca auto-activada; la validación de la propuesta corre ANTES de
+mutar — si la propuesta es inválida, nada cambia)."""
 
 from decimal import Decimal
 
@@ -115,3 +124,102 @@ async def crear_transaccion_manual(
             },
         )
     return tx
+
+
+async def reclasificar_transaccion(
+    *,
+    tx_id: str,
+    rubro_id: str,
+    usuario_id: str,
+    proponer_regla: bool = False,
+    patron: str | None = None,
+) -> Transaccion:
+    """C3: reclasificación manual (ver docstring del módulo)."""
+    try:
+        tid = PydanticObjectId(tx_id)
+    except Exception:
+        raise TransaccionManualError("transaccion_id inválido", 422) from None
+    tx = await Transaccion.get(tid)
+    if tx is None:
+        raise TransaccionManualError("la transacción no existe", 404)
+
+    mc = await MesControl.get(tx.mes_id)
+    if mc is not None and mc.estado is EstadoMes.CERRADO:
+        raise TransaccionManualError(
+            "el mes está cerrado y su histórico es inmutable (regla 4)", 409
+        )
+
+    try:
+        rid = PydanticObjectId(rubro_id)
+    except Exception:
+        raise TransaccionManualError("rubro_id inválido", 422) from None
+    rubro = await Rubro.get(rid)
+    if rubro is None:
+        raise TransaccionManualError("el rubro no existe", 404)
+    if not rubro.activo:
+        raise TransaccionManualError(
+            f"el rubro '{rubro.nombre}' está inactivo (B-2a C1)", 422
+        )
+    if rubro.tipo_flujo is not tx.tipo_flujo:
+        raise TransaccionManualError(
+            f"el rubro '{rubro.nombre}' es {rubro.tipo_flujo.value}, incoherente "
+            f"con una transacción de {tx.tipo_flujo.value} (D1)",
+            409,
+        )
+    if proponer_regla:
+        if patron is None or len(patron.strip()) < 3:
+            raise TransaccionManualError(
+                "proponer_regla exige un patrón de al menos 3 caracteres", 422
+            )
+        # La propuesta se valida ANTES de mutar: si es inválida, nada cambia.
+        from app.reglas.service import _patron_activo_duplicado
+
+        if await _patron_activo_duplicado(patron.strip(), tx.tipo_flujo):
+            raise TransaccionManualError(
+                f"ya existe una regla ACTIVA con el patrón '{patron.strip()}'", 409
+            )
+
+    # Estado previo para la compensación (O1). Inmutables §2.2: NO se tocan.
+    prev_rubro = tx.rubro_id
+    prev_por = tx.clasificada_por
+    prev_at = tx.clasificada_at
+
+    tx.rubro_id = rubro.id
+    tx.clasificada_por = usuario_id
+    tx.clasificada_at = now_utc()
+    await tx.save()
+
+    try:
+        await emit_audit(
+            AuditEvento.transaccion_clasificada,
+            entidad="transaccion",
+            entidad_id=str(tx.id),
+            actor_id=usuario_id,
+            metadata={
+                "origen": "reclasificacion",
+                "rubro_anterior": str(prev_rubro),
+                "rubro_nuevo": str(rubro.id),
+            },
+        )
+    except Exception:
+        # O1: sin rastro no hay reclasificación → compensar.
+        tx.rubro_id = prev_rubro
+        tx.clasificada_por = prev_por
+        tx.clasificada_at = prev_at
+        await tx.save()
+        raise
+
+    if proponer_regla:
+        # §1.9/D5: propuesta APRENDIDA inactiva; la activa el Financiero (/aprobar).
+        from app.reglas.service import ReglasError, proponer_regla_aprendida
+
+        try:
+            await proponer_regla_aprendida(
+                patron=patron.strip(),
+                rubro_id=rubro.id,
+                tipo_flujo=tx.tipo_flujo,
+                usuario_id=usuario_id,
+            )
+        except ReglasError as e:
+            raise TransaccionManualError(e.detalle, e.status) from e
+    return tx
diff --git a/backend/tests/test_audit_events.py b/backend/tests/test_audit_events.py
index 6b3f737..26f3b12 100644
--- a/backend/tests/test_audit_events.py
+++ b/backend/tests/test_audit_events.py
@@ -1,17 +1,19 @@
 # backend/tests/test_audit_events.py
-"""Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001 / CR-S2 / CR-S4.
+"""Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001 / CR-S2 /
+CR-S4 / CR-S5.
 
 29 (Spec §1.11) + extracto.cargado (CR-001) + transaccion.creada (CR-S2, Kimi
 M-1 sprint2-cargas) + rubro.creado/rubro.editado (CR-S4, C1 categorías
-administrables — `rubro.desactivado` ya venía en v1.0) = 33. No se inventan
-eventos sin CR."""
+administrables — `rubro.desactivado` ya venía en v1.0) +
+regla.creada/regla.editada/regla.desactivada (CR-S5, C3 auto-clasificación,
+GO Kimi PLAN-I 9.3) = 36. No se inventan eventos sin CR."""
 
 from app.audit.events import CATALOGO_EVENTOS, AuditEvento
 
 
-def test_catalogo_tiene_exactamente_33_eventos():
-    assert len(AuditEvento) == 33
-    assert len(CATALOGO_EVENTOS) == 33
+def test_catalogo_tiene_exactamente_36_eventos():
+    assert len(AuditEvento) == 36
+    assert len(CATALOGO_EVENTOS) == 36
 
 
 def test_extracto_cargado_es_el_evento_30_de_cr001():
@@ -34,6 +36,9 @@ def test_eventos_clave_presentes():
         "rubro.creado",  # CR-S4 (C1): alta de categoría desde la app
         "rubro.editado",  # CR-S4 (C1): edición (incl. reactivación B-3)
         "rubro.desactivado",  # v1.0: baja lógica (verificado Kimi PLAN-I C1)
+        "regla.creada",  # CR-S5 (C3): alta de regla de clasificación
+        "regla.editada",  # CR-S5 (C3): edición/reactivación/aprobación
+        "regla.desactivada",  # CR-S5 (C3): baja lógica de regla
     ):
         assert esperado in CATALOGO_EVENTOS
 
diff --git a/backend/tests/test_carga.py b/backend/tests/test_carga.py
index 2c72f28..7ecf50b 100644
--- a/backend/tests/test_carga.py
+++ b/backend/tests/test_carga.py
@@ -249,3 +249,104 @@ class TestServicioCarga:
         carga = await self._procesar(tmp_path, [("15-03-2026", "X", -1000)])
         assert carga.archivo_s3_key.startswith("local://")
         assert await AsyncPath(carga.archivo_s3_key.removeprefix("local://")).exists()
+
+    # ── C3: auto-clasificación al cargar (GO Kimi PLAN-I 9.3, lista §5) ──
+
+    async def _regla(self, patron, rubro, prioridad=10, tipo="egreso"):
+        from app.domain.regla_clasificacion import ReglaClasificacion
+
+        r = ReglaClasificacion(
+            patron=patron,
+            rubro_id=rubro.id,
+            tipo_flujo=tipo,
+            prioridad=prioridad,
+            creada_por="u1",
+        )
+        await r.insert()
+        return r
+
+    async def test_carga_clasifica_con_match(self, entorno, tmp_path):
+        # Con match → rubro_id + regla_id escritos (rastro forense §1.5).
+        caf = await Rubro(grupo="operacion", nombre="Cafetería", orden=1).insert()
+        regla = await self._regla("cafeteria", caf)
+        carga = await self._procesar(
+            tmp_path, [("15-03-2026", "COMPRA CAFETERÍA LA 14", -50000)]
+        )
+        assert carga.clasificadas == 1 and carga.por_clasificar == 0
+        tx = await Transaccion.find_one(Transaccion.carga_id == carga.id)
+        assert tx.rubro_id == caf.id
+        assert tx.regla_id == regla.id
+
+    async def test_carga_sin_match_cae_a_por_clasificar(self, entorno, tmp_path):
+        caf = await Rubro(grupo="operacion", nombre="Cafetería", orden=1).insert()
+        await self._regla("cafeteria", caf)
+        carga = await self._procesar(
+            tmp_path, [("15-03-2026", "GASOLINA TEXACO", -80000)]
+        )
+        assert carga.clasificadas == 0 and carga.por_clasificar == 1
+        tx = await Transaccion.find_one(Transaccion.carga_id == carga.id)
+        pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+        assert tx.rubro_id == pc.id
+        assert tx.regla_id is None
+
+    async def test_carga_d2_rubro_inactivo_salta_y_reporta(self, entorno, tmp_path):
+        # D2 (Kimi): regla activa con rubro inactivo → la fila cae a 'Por
+        # clasificar' y la carga reporta reglas_con_rubro_inactivo (fail-loud B-4).
+        caf = await Rubro(
+            grupo="operacion", nombre="Cafetería", orden=1, activo=False
+        ).insert()
+        await self._regla("cafeteria", caf)
+        carga = await self._procesar(
+            tmp_path, [("15-03-2026", "CAFETERIA LA 14", -50000)]
+        )
+        assert carga.clasificadas == 0 and carga.por_clasificar == 1
+        assert carga.reglas_con_rubro_inactivo == ["cafeteria"]
+        tx = await Transaccion.find_one(Transaccion.carga_id == carga.id)
+        pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+        assert tx.rubro_id == pc.id
+
+    async def test_carga_recorrida_identica(self, entorno, tmp_path):
+        # Precedencia determinista: el solape re-cargado (archivo distinto — F-02
+        # rechaza el MISMO archivo por hash) queda como duplicado y NO cambia la
+        # asignación del original; la fila nueva se clasifica igual.
+        caf = await Rubro(grupo="operacion", nombre="Cafetería", orden=1).insert()
+        regla = await self._regla("cafeteria", caf)
+        await self._procesar(tmp_path, [("15-03-2026", "CAFETERIA X", -1000)], "a.xlsx")
+        carga2 = await self._procesar(
+            tmp_path,
+            [
+                ("15-03-2026", "CAFETERIA X", -1000),  # solape → duplicado
+                ("16-03-2026", "CAFETERIA Y", -2000),  # nueva → misma regla
+            ],
+            "b.xlsx",
+        )
+        assert carga2.duplicadas == 1 and carga2.nuevas == 1
+        assert carga2.clasificadas == 1  # contadores SOLO sobre las nuevas
+        txs = await Transaccion.find_all().to_list()
+        assert len(txs) == 2
+        assert all(t.rubro_id == caf.id and t.regla_id == regla.id for t in txs)
+
+    async def test_carga_ingreso_clasifica_a_recaudo(self, entorno, tmp_path):
+        # D1-ii: partición por tipo — la regla de ingreso ('Abono'→Recaudo) solo
+        # ve ingresos; un egreso con texto parecido no se cuela.
+        recaudo = await Rubro(
+            grupo="otros",
+            nombre="Recaudo",
+            tipo_flujo="ingreso",
+            orden=99,
+            es_sistema=True,
+        ).insert()
+        regla = await self._regla("abono", recaudo, tipo="ingreso")
+        carga = await self._procesar(
+            tmp_path,
+            [
+                ("15-03-2026", "ABONO CUOTA SEMANAL", 120000),  # ingreso → Recaudo
+                ("16-03-2026", "PAGO ABONO PROVEEDOR", -90000),  # egreso → PC
+            ],
+        )
+        assert carga.clasificadas == 1 and carga.por_clasificar == 1
+        ing = await Transaccion.find_one(Transaccion.tipo_flujo == "ingreso")
+        egr = await Transaccion.find_one(Transaccion.tipo_flujo == "egreso")
+        pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+        assert ing.rubro_id == recaudo.id and ing.regla_id == regla.id
+        assert egr.rubro_id == pc.id and egr.regla_id is None
diff --git a/backend/tests/test_db.py b/backend/tests/test_db.py
index 3ca293c..c284ec4 100644
--- a/backend/tests/test_db.py
+++ b/backend/tests/test_db.py
@@ -19,7 +19,7 @@ async def test_init_beanie_registra_los_documents_de_dominio():
     from app.domain import DOMAIN_DOCUMENTS, Transaccion
 
     assert mongo.DOCUMENT_MODELS == DOMAIN_DOCUMENTS
-    assert len(DOMAIN_DOCUMENTS) == 7
+    assert len(DOMAIN_DOCUMENTS) == 8  # +ReglaClasificacion (C3, CR-S5)
     assert Transaccion in mongo.DOCUMENT_MODELS
     assert AuditLog not in mongo.DOCUMENT_MODELS
     client = AsyncMongoMockClient()
diff --git a/backend/tests/test_domain_indexes.py b/backend/tests/test_domain_indexes.py
index b139d05..aaf0236 100644
--- a/backend/tests/test_domain_indexes.py
+++ b/backend/tests/test_domain_indexes.py
@@ -44,6 +44,40 @@ async def test_mismo_nombre_distinto_grupo_ok(real_db):
     await Rubro(grupo="otros", nombre="Impuestos", orden=2).insert()  # no colisiona
 
 
+async def test_regla_patron_activo_unico_parcial(real_db):
+    # C3 (regla 7): dos reglas ACTIVAS con mismo (patron_normalizado, tipo_flujo)
+    # → DuplicateKeyError; una DESACTIVADA no cuenta (índice PARCIAL activa=true).
+    from app.domain.regla_clasificacion import ReglaClasificacion
+    from beanie import PydanticObjectId
+
+    rid = PydanticObjectId()
+    inactiva = ReglaClasificacion(
+        patron="Café",
+        rubro_id=rid,
+        tipo_flujo="egreso",
+        prioridad=1,
+        activa=False,
+        creada_por="u",
+    )
+    await inactiva.insert()
+    activa = ReglaClasificacion(
+        patron="cafe",  # mismo normalizado que 'Café'
+        rubro_id=rid,
+        tipo_flujo="egreso",
+        prioridad=2,
+        creada_por="u",
+    )
+    await activa.insert()  # la inactiva NO bloquea
+    with pytest.raises(DuplicateKeyError):
+        await ReglaClasificacion(
+            patron="CAFÉ",
+            rubro_id=rid,
+            tipo_flujo="egreso",
+            prioridad=3,
+            creada_por="u",
+        ).insert()  # segunda ACTIVA idéntica → colisión
+
+
 async def test_configuracion_clave_vigencia_unica(real_db):
     await Configuracion(
         clave="UMBRAL_DIF_BANCO_CIERRE",
diff --git a/backend/tests/test_domain_persistence.py b/backend/tests/test_domain_persistence.py
index 216d36d..7049f83 100644
--- a/backend/tests/test_domain_persistence.py
+++ b/backend/tests/test_domain_persistence.py
@@ -10,14 +10,22 @@ from app.domain import DOMAIN_DOCUMENTS
 from app.domain.configuracion import Configuracion
 from app.domain.mes_control import MesControl
 from app.domain.rubro import Rubro
-from app.domain.seed import seed_configuracion, seed_rubros, seed_rubros_reporte
+from app.domain.seed import (
+    SEMILLA_REGLAS,
+    seed_configuracion,
+    seed_reglas_reporte,
+    seed_rubros,
+    seed_rubros_reporte,
+)
 from beanie import init_beanie
 from mongomock_motor import AsyncMongoMockClient
 
 
 @pytest.fixture
 async def db():
-    client = AsyncMongoMockClient()
+    # tz_aware=True como el Motor real (mongo.create_client): los datetime
+    # re-leídos vuelven UTC-aware (regla 2), no naive.
+    client = AsyncMongoMockClient(tz_aware=True)
     database = client["compas_test"]
     await init_beanie(database=database, document_models=DOMAIN_DOCUMENTS)
     return database
@@ -94,3 +102,40 @@ async def test_seed_configuracion_idempotente(db):
     await seed_configuracion(db)
     total = await Configuracion.find_all().count()
     assert total == 3
+
+
+# ── C3: semilla de reglas de clasificación (GO Kimi PLAN-I 9.3) ──
+
+
+def test_semilla_reglas_sin_pii_y_origen_manual():
+    # Kimi §3 (Ley 1581): SOLO patrones genéricos/comercios — NUNCA nombres de
+    # personas. Lista CONGELADA: las genéricas de ingreso (PRD M7 / MODELO §C3).
+    assert [
+        (r["patron"], r["tipo_flujo"], r["rubro_nombre"]) for r in SEMILLA_REGLAS
+    ] == [
+        ("Abono", "ingreso", "Recaudo"),
+        ("Recibido de", "ingreso", "Recaudo"),
+    ]
+    for r in SEMILLA_REGLAS:
+        assert r["origen"] == "manual"  # curaduría, no aprendizaje (Kimi §3)
+
+
+async def test_seed_reglas_idempotente_y_resuelve_rubro(db):
+    from app.domain.regla_clasificacion import ReglaClasificacion
+
+    await seed_rubros(db)  # siembra 'Recaudo' primero
+    n1, col1 = await seed_reglas_reporte(db)
+    n2, col2 = await seed_reglas_reporte(db)
+    assert n1 == 2 and col1 == []
+    assert n2 == 0 and len(col2) == 2  # 2ª corrida: no duplica
+    reglas = await ReglaClasificacion.find_all().to_list()
+    assert len(reglas) == 2
+    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo")
+    assert all(r.rubro_id == recaudo.id for r in reglas)
+    assert all(r.activa for r in reglas)
+
+
+async def test_seed_reglas_fail_loud_sin_rubro_destino(db):
+    # Kimi §3: si el rubro destino del mapeo no existe → error, no silencio.
+    with pytest.raises(LookupError):
+        await seed_reglas_reporte(db)  # sin sembrar rubros primero
diff --git a/backend/tests/test_domain_regla.py b/backend/tests/test_domain_regla.py
new file mode 100644
index 0000000..7ed48b1
--- /dev/null
+++ b/backend/tests/test_domain_regla.py
@@ -0,0 +1,89 @@
+# backend/tests/test_domain_regla.py
+"""ReglaClasificacion (Spec §1.9, C3, GO Kimi PLAN-I 9.3) + normalización única.
+
+La normalización compartida (case-insensitive + sin tildes) es EL punto delicado
+de la pieza (Kimi §3): la misma función normaliza el patrón al escribir la regla y
+la descripción al matchear — el test cubre tilde↔sin-tilde y case en AMBAS
+direcciones."""
+
+import pytest
+from app.domain.regla_clasificacion import (
+    OrigenRegla,
+    ReglaClasificacion,
+    coincide,
+    normalizar_texto,
+)
+from beanie import PydanticObjectId
+from pydantic import ValidationError
+
+# ── Normalización única compartida (Kimi: test exigido, ambas direcciones) ──
+
+
+def test_normalizar_case_y_tildes():
+    assert normalizar_texto("Café") == "cafe"
+    assert normalizar_texto("CAFETERÍA LA 14") == "cafeteria la 14"
+    assert normalizar_texto("  Peaje  ") == "peaje"
+
+
+def test_match_tilde_patron_contra_descripcion_sin_tilde():
+    # Patrón "Café" matchea "CAFETERIA LA 14" (patrón con tilde, descripción sin).
+    assert coincide("Café", "CAFETERIA LA 14")
+
+
+def test_match_sin_tilde_patron_contra_descripcion_con_tilde():
+    # Dirección inversa: patrón sin tilde matchea descripción con tilde.
+    assert coincide("cafeteria", "Compra CAFETERÍA central")
+
+
+def test_match_case_ambas_direcciones():
+    assert coincide("PEAJE", "pago peaje ruta 40")
+    assert coincide("peaje", "PAGO PEAJE RUTA 40")
+
+
+def test_no_match():
+    assert not coincide("gasolina", "CAFETERIA LA 14")
+
+
+# ── Modelo (Spec §1.9) ──
+
+
+def _regla(**over):
+    base = {
+        "patron": "Cafetería",
+        "rubro_id": PydanticObjectId(),
+        "tipo_flujo": "egreso",
+        "prioridad": 10,
+        "creada_por": "u1",
+    }
+    base.update(over)
+    return ReglaClasificacion(**base)
+
+
+def test_regla_valida_deriva_patron_normalizado():
+    r = _regla()
+    assert r.patron == "Cafetería"
+    assert r.patron_normalizado == "cafeteria"
+    assert r.origen is OrigenRegla.MANUAL
+    assert r.activa is True
+
+
+def test_patron_minimo_3_caracteres():
+    # Guarda contra match-all (Kimi §3): 2 chars → inválido.
+    with pytest.raises(ValidationError):
+        _regla(patron="ab")
+
+
+def test_patron_max_120():
+    with pytest.raises(ValidationError):
+        _regla(patron="x" * 121)
+
+
+def test_strict_rechaza_campo_extra():
+    with pytest.raises(ValidationError):
+        _regla(inventado=1)
+
+
+def test_origen_aprendida_valido():
+    r = _regla(origen="aprendida", activa=False)
+    assert r.origen is OrigenRegla.APRENDIDA
+    assert r.activa is False
diff --git a/backend/tests/test_rbac_permissions.py b/backend/tests/test_rbac_permissions.py
index 5679bc2..a78c77c 100644
--- a/backend/tests/test_rbac_permissions.py
+++ b/backend/tests/test_rbac_permissions.py
@@ -22,6 +22,8 @@ CANONICA: dict[str, set[Role]] = {
     "capacidad_pago:ver": {Role.financiero, Role.directivo, Role.admin},
     # CR-S4 (C1 categorías administrables): gestión del catálogo de rubros
     "rubros:gestionar": {Role.financiero, Role.admin},
+    # CR-S5 (C3 auto-clasificación): gestión de reglas de clasificación
+    "reglas:gestionar": {Role.financiero, Role.admin},
     # §2.4 — autoridad del ciclo (manda sobre §4.1)
     "ciclo:abrir": {Role.financiero, Role.directivo, Role.admin},
     "ciclo:proponer": {Role.financiero, Role.directivo, Role.admin},
diff --git a/backend/tests/test_reglas_endpoints.py b/backend/tests/test_reglas_endpoints.py
new file mode 100644
index 0000000..cc9e124
--- /dev/null
+++ b/backend/tests/test_reglas_endpoints.py
@@ -0,0 +1,542 @@
+# backend/tests/test_reglas_endpoints.py
+"""C3 auto-clasificación — /api/v1/reglas-clasificacion (GO Kimi PLAN-I 9.3, CR-S5).
+
+MARCADO PARA AUDITORÍA KIMI (gate I-PR1; lista §5 del veredicto PLAN-I).
+
+Cubre: D1 coherencia tipo regla↔rubro al crear/editar Y al activar/aprobar (B-1);
+precedencia determinista (prioridad asc + _id); unicidad de patrón activo;
+aprendidas nunca auto-activadas (§1.9); aplicar-pendientes solo 'Por clasificar'
+de meses NO cerrados, idempotente y SELLADO con clasificada_por/at + regla_id
+(B-2); RBAC exacto; O1 fail-closed con compensación (estándar C1/B-5).
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
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.regla_clasificacion import ReglaClasificacion
+from app.domain.rubro import Rubro
+from app.domain.transaccion import Transaccion
+from app.main import create_app
+from app.reglas.service import elegir_regla
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+PWD = "clave-larga-1234"
+BASE = "/api/v1/reglas-clasificacion"
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
+    await Rubro(
+        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
+    ).insert()
+    await Rubro(
+        grupo="otros",
+        nombre="Recaudo",
+        tipo_flujo="ingreso",
+        orden=99,
+        es_sistema=True,
+    ).insert()
+    await Rubro(grupo="operacion", nombre="Cafetería", orden=1).insert()
+    await Rubro(grupo="operacion", nombre="Transporte", orden=2).insert()
+    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()
+    await MesControl(
+        mes="2026-01-01", saldo_inicial_caja=Decimal("0"), estado=EstadoMes.CERRADO
+    ).insert()
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
+async def _crear(ac, h, patron="Cafetería", rubro=None, tipo="egreso", prioridad=10):
+    if rubro is None:
+        rubro = await _rubro("Cafetería")
+    return await ac.post(
+        BASE,
+        json={
+            "patron": patron,
+            "rubro_id": str(rubro.id),
+            "tipo_flujo": tipo,
+            "prioridad": prioridad,
+        },
+        headers=h,
+    )
+
+
+# ────────────── elegir_regla (precedencia determinista, unitario) ──────────────
+
+
+async def test_precedencia_gana_menor_prioridad(api):
+    caf = await _rubro("Cafetería")
+    tra = await _rubro("Transporte")
+    r1 = ReglaClasificacion(
+        patron="pago", rubro_id=tra.id, tipo_flujo="egreso", prioridad=5, creada_por="u"
+    )
+    r2 = ReglaClasificacion(
+        patron="cafe", rubro_id=caf.id, tipo_flujo="egreso", prioridad=1, creada_por="u"
+    )
+    await r1.insert()
+    await r2.insert()
+    activos = {caf.id, tra.id}
+    # Ambas matchean; gana la de prioridad 1 (cafe), no la de 5.
+    elegida = elegir_regla("PAGO CAFETERIA LA 14", [r1, r2], activos)
+    assert elegida is not None and elegida.id == r2.id
+
+
+async def test_precedencia_empate_desempata_por_id(api):
+    caf = await _rubro("Cafetería")
+    tra = await _rubro("Transporte")
+    a = ReglaClasificacion(
+        patron="pago", rubro_id=caf.id, tipo_flujo="egreso", prioridad=1, creada_por="u"
+    )
+    b = ReglaClasificacion(
+        patron="pag", rubro_id=tra.id, tipo_flujo="egreso", prioridad=1, creada_por="u"
+    )
+    await a.insert()
+    await b.insert()
+    activos = {caf.id, tra.id}
+    primero = min([a, b], key=lambda r: (r.prioridad, str(r.id)))
+    # Determinista: siempre el mismo, pase lo que pase con el orden de entrada.
+    assert elegir_regla("pago x", [a, b], activos).id == primero.id
+    assert elegir_regla("pago x", [b, a], activos).id == primero.id
+
+
+async def test_elegir_salta_rubro_inactivo_d2(api):
+    caf = await _rubro("Cafetería")
+    r = ReglaClasificacion(
+        patron="cafe", rubro_id=caf.id, tipo_flujo="egreso", prioridad=1, creada_por="u"
+    )
+    await r.insert()
+    # rubro NO está en el set de activos → la regla se salta (D2).
+    assert elegir_regla("CAFETERIA", [r], set()) is None
+
+
+# ────────────────────────────── POST (crear) ──────────────────────────────
+
+
+async def test_post_crea_y_emite_regla_creada(api):
+    ac, c = api
+    h = await _token(ac)
+    r = await _crear(ac, h, patron="Café", prioridad=7)
+    assert r.status_code == 201
+    d = r.json()
+    assert d["patron"] == "Café"
+    assert d["patron_normalizado"] == "cafe"
+    assert d["origen"] == "manual"
+    assert d["activa"] is True
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.creada"})
+    assert ev is not None and ev["entidad_id"] == d["id"]
+
+
+async def test_post_patron_2_chars_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await _crear(ac, h, patron="ab")
+    assert r.status_code == 422
+
+
+async def test_post_rubro_de_otro_tipo_409_d1(api):
+    # D1: regla de egreso apuntando a 'Recaudo' (ingreso) → 409.
+    ac, _ = api
+    h = await _token(ac)
+    recaudo = await _rubro("Recaudo")
+    r = await _crear(ac, h, rubro=recaudo, tipo="egreso")
+    assert r.status_code == 409
+
+
+async def test_post_rubro_inactivo_422_d1(api):
+    ac, _ = api
+    h = await _token(ac)
+    caf = await _rubro("Cafetería")
+    caf.activo = False
+    await caf.save()
+    r = await _crear(ac, h)
+    assert r.status_code == 422
+
+
+async def test_post_rubro_inexistente_404(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        BASE,
+        json={
+            "patron": "cafe",
+            "rubro_id": "64b000000000000000000000",
+            "tipo_flujo": "egreso",
+            "prioridad": 1,
+        },
+        headers=h,
+    )
+    assert r.status_code == 404
+
+
+async def test_post_patron_activo_duplicado_409(api):
+    # Unicidad (patron_normalizado, tipo_flujo) activa — "Café" ≡ "cafe".
+    ac, _ = api
+    h = await _token(ac)
+    assert (await _crear(ac, h, patron="Café")).status_code == 201
+    r = await _crear(ac, h, patron="cafe", prioridad=99)
+    assert r.status_code == 409
+
+
+async def test_precheck_duplicado_desactivado_no_cuenta(api):
+    # La desactivada no bloquea una nueva activa con el mismo patrón. El pre-check
+    # se prueba aquí (unitario); el ÍNDICE parcial real, en test_domain_indexes
+    # (@requires_real_mongo — mongomock PIERDE el partialFilterExpression al crear
+    # el índice vía Beanie y lo aplica como único TOTAL: se tumba aquí para poder
+    # coexistir activa+inactiva, que es exactamente el caso del parcial real).
+    from app.domain.rubro import TipoFlujo
+    from app.reglas.service import _patron_activo_duplicado
+
+    ac, c = api
+    await c["compas_test"]["reglas_clasificacion"].drop_index(
+        "patron_tipo_activa_unico"
+    )
+    caf = await _rubro("Cafetería")
+    await ReglaClasificacion(
+        patron="Café",
+        rubro_id=caf.id,
+        tipo_flujo="egreso",
+        prioridad=1,
+        activa=False,
+        creada_por="u",
+    ).insert()
+    assert not await _patron_activo_duplicado("cafe", TipoFlujo.EGRESO)
+    await ReglaClasificacion(
+        patron="cafe",
+        rubro_id=caf.id,
+        tipo_flujo="egreso",
+        prioridad=2,
+        creada_por="u",
+    ).insert()
+    assert await _patron_activo_duplicado("CAFÉ", TipoFlujo.EGRESO)
+    # Otro tipo_flujo no colisiona (la partición D1-ii también parte la unicidad).
+    assert not await _patron_activo_duplicado("cafe", TipoFlujo.INGRESO)
+
+
+# ────────────────────────────── PATCH (editar) ──────────────────────────────
+
+
+async def test_patch_edita_y_emite_regla_editada(api):
+    ac, c = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]
+    r = await ac.patch(f"{BASE}/{rid}", json={"prioridad": 3}, headers=h)
+    assert r.status_code == 200
+    assert r.json()["prioridad"] == 3
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.editada"})
+    assert ev is not None
+    assert ev["metadata"]["cambios"]["prioridad"] == {"anterior": 10, "nuevo": 3}
+
+
+async def test_patch_patron_rederiva_normalizado(api):
+    ac, _ = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]
+    r = await ac.patch(f"{BASE}/{rid}", json={"patron": "Peaje Túnel"}, headers=h)
+    assert r.status_code == 200
+    assert r.json()["patron_normalizado"] == "peaje tunel"
+
+
+async def test_patch_rubro_de_otro_tipo_409_d1(api):
+    ac, _ = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]
+    recaudo = await _rubro("Recaudo")
+    r = await ac.patch(f"{BASE}/{rid}", json={"rubro_id": str(recaudo.id)}, headers=h)
+    assert r.status_code == 409
+
+
+async def test_patch_activa_false_422_usa_desactivar(api):
+    ac, _ = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]
+    r = await ac.patch(f"{BASE}/{rid}", json={"activa": False}, headers=h)
+    assert r.status_code == 422
+
+
+async def test_patch_reactivar_revalida_rubro_b1(api):
+    # B-1 Kimi: el rubro pudo desactivarse ENTRE la creación y la reactivación.
+    ac, _ = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]
+    await ac.post(f"{BASE}/{rid}/desactivar", headers=h)
+    caf = await _rubro("Cafetería")
+    caf.activo = False
+    await caf.save()
+    r = await ac.patch(f"{BASE}/{rid}", json={"activa": True}, headers=h)
+    assert r.status_code == 409  # activar hacia rubro inactivo, prohibido
+
+
+async def test_patch_reactivar_ok_emite_editada(api):
+    ac, c = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]
+    await ac.post(f"{BASE}/{rid}/desactivar", headers=h)
+    r = await ac.patch(f"{BASE}/{rid}", json={"activa": True}, headers=h)
+    assert r.status_code == 200 and r.json()["activa"] is True
+    evs = await c["compas_test"]["audit_log"].count_documents(
+        {"evento": "regla.editada"}
+    )
+    assert evs == 1
+
+
+# ────────────────────────── desactivar / aprobar ──────────────────────────
+
+
+async def test_desactivar_emite_regla_desactivada(api):
+    ac, c = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]
+    r = await ac.post(f"{BASE}/{rid}/desactivar", headers=h)
+    assert r.status_code == 200 and r.json()["activa"] is False
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.desactivada"})
+    assert ev is not None
+    # Ya inactiva → 409 explícito.
+    assert (await ac.post(f"{BASE}/{rid}/desactivar", headers=h)).status_code == 409
+
+
+async def _proponer_aprendida(activa=False) -> ReglaClasificacion:
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    regla = ReglaClasificacion(
+        patron="cafeteria",
+        rubro_id=caf.id,
+        tipo_flujo="egreso",
+        prioridad=50,
+        origen="aprendida",
+        activa=activa,
+        creada_por="u1",
+    )
+    await regla.insert()
+    return regla
+
+
+async def test_aprobar_aprendida_emite_editada_via_aprobacion(api):
+    ac, c = api
+    h = await _token(ac)
+    regla = await _proponer_aprendida()
+    r = await ac.post(f"{BASE}/{regla.id}/aprobar", headers=h)
+    assert r.status_code == 200 and r.json()["activa"] is True
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.editada"})
+    assert ev is not None
+    assert ev["metadata"]["cambios"]["activa"] == {"anterior": False, "nuevo": True}
+    assert ev["metadata"]["via"] == "aprobacion"
+
+
+async def test_aprobar_manual_409(api):
+    ac, _ = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]  # origen manual
+    r = await ac.post(f"{BASE}/{rid}/aprobar", headers=h)
+    assert r.status_code == 409
+
+
+async def test_aprobar_ya_activa_409(api):
+    ac, _ = api
+    h = await _token(ac)
+    regla = await _proponer_aprendida(activa=True)
+    r = await ac.post(f"{BASE}/{regla.id}/aprobar", headers=h)
+    assert r.status_code == 409
+
+
+async def test_aprobar_con_rubro_inactivo_409_b1(api):
+    # B-1 Kimi: la activación exige rubro existente + activo + tipo coherente.
+    ac, _ = api
+    h = await _token(ac)
+    regla = await _proponer_aprendida()
+    caf = await _rubro("Cafetería")
+    caf.activo = False
+    await caf.save()
+    r = await ac.post(f"{BASE}/{regla.id}/aprobar", headers=h)
+    assert r.status_code == 409
+
+
+# ────────────────────────── aplicar-pendientes (B-2) ──────────────────────────
+
+
+async def _tx_por_clasificar(fecha: str, descripcion: str, tipo="egreso"):
+    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+    mc = await MesControl.find_one(MesControl.mes == fecha[:7] + "-01")
+    tx = Transaccion(
+        fecha=fecha,
+        descripcion=descripcion,
+        valor=Decimal("10000"),
+        tipo_flujo=tipo,
+        rubro_id=pc.id,
+        mes_id=mc.id,
+        banco="manual",
+        id_banco=f"MAN-{descripcion[:20]}-{fecha}",
+    )
+    await tx.insert()
+    return tx
+
+
+async def test_aplicar_pendientes_clasifica_y_sella_b2(api):
+    ac, _ = api
+    h = await _token(ac)
+    await _crear(ac, h, patron="cafeteria")
+    tx = await _tx_por_clasificar("2026-03-10", "COMPRA CAFETERÍA LA 14")
+    r = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
+    assert r.status_code == 200
+    assert r.json()["clasificadas"] == 1
+    caf = await _rubro("Cafetería")
+    despues = await Transaccion.get(tx.id)
+    assert despues.rubro_id == caf.id
+    assert despues.regla_id is not None  # rastro forense §1.5
+    # B-2 (Kimi): sellado por documento — quién disparó el lote y cuándo.
+    assert despues.clasificada_por is not None
+    assert despues.clasificada_at is not None
+
+
+async def test_aplicar_pendientes_no_toca_mes_cerrado(api):
+    # Regla 4: 'Por clasificar' de un mes CERRADO no se reclasifica.
+    ac, _ = api
+    h = await _token(ac)
+    await _crear(ac, h, patron="cafeteria")
+    tx = await _tx_por_clasificar("2026-01-10", "CAFETERIA CENTRO")
+    r = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
+    assert r.status_code == 200
+    assert r.json()["clasificadas"] == 0
+    pc = await _rubro("Por clasificar")
+    assert (await Transaccion.get(tx.id)).rubro_id == pc.id  # intacta
+
+
+async def test_aplicar_pendientes_idempotente_y_no_toca_clasificadas(api):
+    ac, _ = api
+    h = await _token(ac)
+    await _crear(ac, h, patron="cafeteria")
+    await _tx_por_clasificar("2026-03-10", "CAFETERIA LA 14")
+    r1 = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
+    assert r1.json()["clasificadas"] == 1
+    r2 = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
+    assert r2.json()["clasificadas"] == 0  # lo ya clasificado no se toca
+    assert r2.json()["sin_match"] == 0
+
+
+async def test_aplicar_pendientes_sin_match_queda_por_clasificar(api):
+    ac, _ = api
+    h = await _token(ac)
+    await _crear(ac, h, patron="cafeteria")
+    tx = await _tx_por_clasificar("2026-03-10", "GASOLINA TEXACO")
+    r = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
+    assert r.json()["clasificadas"] == 0 and r.json()["sin_match"] == 1
+    pc = await _rubro("Por clasificar")
+    assert (await Transaccion.get(tx.id)).rubro_id == pc.id
+
+
+# ────────────────────────────── RBAC exacto ──────────────────────────────
+
+
+@pytest.mark.parametrize(
+    "email",
+    ["consulta@roddos.com", "fin@roddos.com", "dir@roddos.com", "admin@roddos.com"],
+)
+async def test_get_200_los_cuatro_roles(api, email):
+    ac, _ = api
+    h = await _token(ac, email)
+    assert (await ac.get(BASE, headers=h)).status_code == 200
+
+
+@pytest.mark.parametrize("email", ["consulta@roddos.com", "dir@roddos.com"])
+async def test_mutaciones_403_consulta_y_directivo(api, email):
+    ac, _ = api
+    hf = await _token(ac)  # financiero prepara una regla
+    rid = (await _crear(ac, hf)).json()["id"]
+    h = await _token(ac, email)
+    assert (await _crear(ac, h, patron="otra")).status_code == 403
+    assert (
+        await ac.patch(f"{BASE}/{rid}", json={"prioridad": 1}, headers=h)
+    ).status_code == 403
+    assert (await ac.post(f"{BASE}/{rid}/desactivar", headers=h)).status_code == 403
+    assert (await ac.post(f"{BASE}/{rid}/aprobar", headers=h)).status_code == 403
+    assert (await ac.post(f"{BASE}/aplicar-pendientes", headers=h)).status_code == 403
+
+
+# ────────────────────────── O1 fail-closed (B-5 C1) ──────────────────────────
+
+
+async def test_fail_closed_crear_compensa(api, monkeypatch):
+    ac, _ = api
+    h = await _token(ac)
+
+    async def _boom(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr("app.reglas.service.emit_audit", _boom)
+    with pytest.raises(RuntimeError):
+        await _crear(ac, h)
+    assert await ReglaClasificacion.find_one() is None
+
+
+async def test_fail_closed_aprobar_compensa(api, monkeypatch):
+    ac, _ = api
+    h = await _token(ac)
+    regla = await _proponer_aprendida()
+
+    async def _boom(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr("app.reglas.service.emit_audit", _boom)
+    with pytest.raises(RuntimeError):
+        await ac.post(f"{BASE}/{regla.id}/aprobar", headers=h)
+    assert (await ReglaClasificacion.get(regla.id)).activa is False  # revertido
+
+
+async def test_fail_closed_desactivar_compensa(api, monkeypatch):
+    ac, _ = api
+    h = await _token(ac)
+    rid = (await _crear(ac, h)).json()["id"]
+
+    async def _boom(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr("app.reglas.service.emit_audit", _boom)
+    with pytest.raises(RuntimeError):
+        await ac.post(f"{BASE}/{rid}/desactivar", headers=h)
+    regla = await ReglaClasificacion.find_one()
+    assert regla.activa is True  # revertido
diff --git a/backend/tests/test_transacciones_clasificar.py b/backend/tests/test_transacciones_clasificar.py
new file mode 100644
index 0000000..c4ecb48
--- /dev/null
+++ b/backend/tests/test_transacciones_clasificar.py
@@ -0,0 +1,244 @@
+# backend/tests/test_transacciones_clasificar.py
+"""C3 — PATCH /api/v1/transacciones/{id}/clasificar (GO Kimi PLAN-I 9.3).
+
+MARCADO PARA AUDITORÍA KIMI (gate I-PR1; lista §5).
+
+Reclasificación MANUAL: mes cerrado → 409 (regla 4); rubro inexistente → 404,
+inactivo → 422, tipo incoherente → 409 (D1); OK → `transaccion.clasificada` con
+{rubro_anterior→nuevo}; fecha/valor/banco/id_banco INTACTOS (Spec §2.2, assert
+explícito). `proponer_regla:true` → ReglaClasificacion aprendida con activa=False
+FORZADO (§1.9: nunca auto-activada) + `regla.creada`.
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
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.regla_clasificacion import ReglaClasificacion
+from app.domain.rubro import Rubro
+from app.domain.transaccion import Transaccion
+from app.main import create_app
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+PWD = "clave-larga-1234"
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
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
+    for correo, rol in [
+        ("consulta@roddos.com", Role.consulta),
+        ("fin@roddos.com", Role.financiero),
+    ]:
+        await repository.create_user(
+            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
+        )
+    await Rubro(
+        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
+    ).insert()
+    await Rubro(grupo="operacion", nombre="Cafetería", orden=1).insert()
+    await Rubro(
+        grupo="otros",
+        nombre="Recaudo",
+        tipo_flujo="ingreso",
+        orden=99,
+        es_sistema=True,
+    ).insert()
+    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()
+    await MesControl(
+        mes="2026-01-01", saldo_inicial_caja=Decimal("0"), estado=EstadoMes.CERRADO
+    ).insert()
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
+async def _tx(fecha="2026-03-15", tipo="egreso") -> Transaccion:
+    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+    mc = await MesControl.find_one(MesControl.mes == fecha[:7] + "-01")
+    tx = Transaccion(
+        fecha=fecha,
+        descripcion="COMPRA CAFETERIA LA 14",
+        valor=Decimal("50000"),
+        tipo_flujo=tipo,
+        rubro_id=pc.id,
+        mes_id=mc.id,
+        banco="manual",
+        id_banco=f"MAN-CLASIF-{fecha}",
+    )
+    await tx.insert()
+    return tx
+
+
+async def _clasificar(ac, h, tx_id, rubro_id, **extra):
+    return await ac.patch(
+        f"/api/v1/transacciones/{tx_id}/clasificar",
+        json={"rubro_id": str(rubro_id), **extra},
+        headers=h,
+    )
+
+
+async def test_clasificar_ok_emite_evento_con_anterior_y_nuevo(api):
+    ac, c = api
+    h = await _token(ac)
+    tx = await _tx()
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+    r = await _clasificar(ac, h, tx.id, caf.id)
+    assert r.status_code == 200
+    assert r.json()["rubro_id"] == str(caf.id)
+    despues = await Transaccion.get(tx.id)
+    assert despues.rubro_id == caf.id
+    assert despues.clasificada_por is not None
+    assert despues.clasificada_at is not None
+    ev = await c["compas_test"]["audit_log"].find_one(
+        {"evento": "transaccion.clasificada"}
+    )
+    assert ev is not None and ev["entidad_id"] == str(tx.id)
+    assert ev["metadata"]["rubro_anterior"] == str(pc.id)
+    assert ev["metadata"]["rubro_nuevo"] == str(caf.id)
+
+
+async def test_clasificar_inmutables_intactos(api):
+    # Spec §2.2 (assert explícito de Kimi): fecha/valor/banco/id_banco no cambian.
+    ac, _ = api
+    h = await _token(ac)
+    tx = await _tx()
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    await _clasificar(ac, h, tx.id, caf.id)
+    d = await Transaccion.get(tx.id)
+    assert d.fecha == tx.fecha
+    assert d.valor == tx.valor
+    assert d.banco == tx.banco
+    assert d.id_banco == tx.id_banco
+    assert d.tipo_flujo == tx.tipo_flujo
+
+
+async def test_clasificar_mes_cerrado_409(api):
+    # Regla 4: el histórico congelado no se reclasifica.
+    ac, _ = api
+    h = await _token(ac)
+    tx = await _tx(fecha="2026-01-15")
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    r = await _clasificar(ac, h, tx.id, caf.id)
+    assert r.status_code == 409
+
+
+async def test_clasificar_rubro_inactivo_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    tx = await _tx()
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    caf.activo = False
+    await caf.save()
+    r = await _clasificar(ac, h, tx.id, caf.id)
+    assert r.status_code == 422
+
+
+async def test_clasificar_tipo_incoherente_409_d1(api):
+    # Transacción de egreso hacia 'Recaudo' (ingreso) → 409.
+    ac, _ = api
+    h = await _token(ac)
+    tx = await _tx(tipo="egreso")
+    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo")
+    r = await _clasificar(ac, h, tx.id, recaudo.id)
+    assert r.status_code == 409
+
+
+async def test_clasificar_rubro_inexistente_404(api):
+    ac, _ = api
+    h = await _token(ac)
+    tx = await _tx()
+    r = await _clasificar(ac, h, tx.id, "64b000000000000000000000")
+    assert r.status_code == 404
+
+
+async def test_clasificar_transaccion_inexistente_404(api):
+    ac, _ = api
+    h = await _token(ac)
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    r = await _clasificar(ac, h, "64b000000000000000000000", caf.id)
+    assert r.status_code == 404
+
+
+async def test_proponer_regla_crea_aprendida_inactiva(api):
+    # §1.9/D5: la propuesta nace activa=False SIEMPRE + regla.creada.
+    ac, c = api
+    h = await _token(ac)
+    tx = await _tx()
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    r = await _clasificar(
+        ac, h, tx.id, caf.id, proponer_regla=True, patron="cafeteria la 14"
+    )
+    assert r.status_code == 200
+    regla = await ReglaClasificacion.find_one()
+    assert regla is not None
+    assert regla.origen.value == "aprendida"
+    assert regla.activa is False  # NUNCA auto-activada
+    assert regla.rubro_id == caf.id
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.creada"})
+    assert ev is not None and ev["metadata"]["origen"] == "aprendida"
+
+
+async def test_proponer_regla_sin_patron_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    tx = await _tx()
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    r = await _clasificar(ac, h, tx.id, caf.id, proponer_regla=True)
+    assert r.status_code == 422
+
+
+async def test_clasificar_consulta_403(api):
+    ac, _ = api
+    h = await _token(ac, "consulta@roddos.com")
+    tx = await _tx()
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    r = await _clasificar(ac, h, tx.id, caf.id)
+    assert r.status_code == 403
+
+
+async def test_fail_closed_clasificar_compensa(api, monkeypatch):
+    # O1: si el emit de transaccion.clasificada falla, el rubro se revierte.
+    ac, _ = api
+    h = await _token(ac)
+    tx = await _tx()
+    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
+    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+
+    async def _boom(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr("app.transacciones.service.emit_audit", _boom)
+    with pytest.raises(RuntimeError):
+        await _clasificar(ac, h, tx.id, caf.id)
+    assert (await Transaccion.get(tx.id)).rubro_id == pc.id  # revertido
diff --git a/migrations/20260722_seed_reglas_clasificacion.py b/migrations/20260722_seed_reglas_clasificacion.py
new file mode 100644
index 0000000..88e3ccd
--- /dev/null
+++ b/migrations/20260722_seed_reglas_clasificacion.py
@@ -0,0 +1,55 @@
+#!/usr/bin/env python
+"""Migración idempotente: semilla de reglas de clasificación (C3, CR-S5).
+
+GO Kimi PLAN-I 9.3. Siembra las reglas genéricas de ingreso ('Abono',
+'Recibido de' → 'Recaudo', PRD M7 / MODELO §C3). SOLO patrones genéricos — NUNCA
+nombres de personas (Ley 1581). $setOnInsert por (patron_normalizado, tipo_flujo):
+re-correr no duplica ni pisa. FAIL-LOUD si un rubro destino no existe (correr
+seed_rubros primero). Imprime el reporte de colisiones (B-4).
+
+B-1 I-PR1 C1 (patrón de migraciones): la URI se lee de la VARIABLE DE ENTORNO
+`MONGODB_URI` — nunca por argv (visible en ps/historial).
+
+Uso:  MONGODB_URI="<uri>" python migrations/20260722_seed_reglas_clasificacion.py [db=compas]
+"""
+
+from __future__ import annotations
+
+import asyncio
+import os
+import sys
+
+sys.path.insert(0, "backend")
+
+from app.db import mongo  # noqa: E402
+from app.domain.seed import seed_reglas_reporte  # noqa: E402
+
+
+async def _run(uri: str, db_name: str) -> None:
+    client = mongo.create_client(uri)
+    await mongo.init_beanie_for(client, db_name)
+    insertadas, colisiones = await seed_reglas_reporte(client[db_name])
+    print(f"[reglas] {insertadas} nuevas insertadas (idempotente).")
+    if colisiones:
+        print(f"[reglas] {len(colisiones)} colisiones (doc preexistente, NO tocado):")
+        for c in colisiones:
+            print(f"  - ({c['patron_normalizado']}, {c['tipo_flujo']})")
+    else:
+        print("[reglas] sin colisiones.")
+    client.close()
+
+
+def main() -> None:
+    uri = os.environ.get("MONGODB_URI")
+    if not uri:
+        sys.exit(
+            "Falta MONGODB_URI en el entorno.\n"
+            'Uso: MONGODB_URI="<uri>" python '
+            "migrations/20260722_seed_reglas_clasificacion.py [db=compas]"
+        )
+    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
+    asyncio.run(_run(uri, db_name))
+
+
+if __name__ == "__main__":
+    main()

```
