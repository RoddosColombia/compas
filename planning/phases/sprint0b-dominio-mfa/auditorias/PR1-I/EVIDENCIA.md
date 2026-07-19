# EVIDENCIA — sprint0b-dominio-mfa · I-PR1

Commit `203e23f` en rama `sprint0b-dominio-mfa`. Trae el código real + salidas de tests (no descripciones).

## 1. Salida de pytest (suite completa)

```
129 passed, 9 skipped, 9 warnings in ~79s
SKIPPED (todos @requires_real_mongo): test_domain_indexes[3], test_audit_immutable[3], test_auth_concurrency[1], test_auth_indexes[1], test_real_mongo_marker[1]
```

## 2. ruff

```
All checks passed!
```

## 3. Self-check de la semilla (al peso)

```
total rubros: 32
por grupo: {'costo_producto': 3, 'operacion': 11, 'nomina': 6, 'deudas_obligaciones': 5, 'otros': 7}
de sistema: ['Por clasificar', 'Ajuste de conciliación']
tipo_flujo distinct: {'egreso'}
ordenes 1..32: True
config claves: ['UMBRAL_DIF_BANCO_CIERRE', 'CALENDARIO_DIAN', 'DIAS_CREDITO_POR_PROVEEDOR']
```

## 4. git show --stat (commit 203e23f)

```
203e23f feat(dominio): PR-1 Sprint 0b — Rubro+semilla real, MesControl, Configuracion, init_beanie
 backend/app/api/v1/health.py               |  24 ++++-
 backend/app/core/money.py                  |  43 ++++++++
 backend/app/db/mongo.py                    |  33 ++++---
 backend/app/domain/__init__.py             |  16 +++
 backend/app/domain/configuracion.py        | 127 ++++++++++++++++++++++++
 backend/app/domain/mes_control.py          | 100 +++++++++++++++++++
 backend/app/domain/rubro.py                | 151 +++++++++++++++++++++++++++++
 backend/app/domain/seed.py                 |  59 +++++++++++
 backend/app/main.py                        |  24 ++++-
 backend/tests/conftest.py                  |  30 +++++-
 backend/tests/test_db.py                   |  15 ++-
 backend/tests/test_domain_configuracion.py |  97 ++++++++++++++++++
 backend/tests/test_domain_indexes.py       |  58 +++++++++++
 backend/tests/test_domain_mes_control.py   |  67 +++++++++++++
 backend/tests/test_domain_money.py         |  48 +++++++++
 backend/tests/test_domain_persistence.py   |  66 +++++++++++++
 backend/tests/test_domain_rubro.py         |  94 ++++++++++++++++++
 backend/tests/test_init_beanie_wiring.py   |  54 +++++++++++
 docs/Calendario_DIAN_2026.md               |  35 +++++++
 migrations/20260901_seed_configuracion.py  |  41 ++++++++
 migrations/20260901_seed_rubros.py         |  40 ++++++++
 21 files changed, 1194 insertions(+), 28 deletions(-)
```

## 5. Código fuente — módulos nuevos

### `backend/app/core/money.py`

```python
# backend/app/core/money.py
"""Tipo Money — dinero como Decimal, NUNCA float (regla 1 de CLAUDE.md).

Problema real que resuelve (cazado en Sprint 0b): BSON persiste `Decimal` como
`bson.Decimal128`; al releer desde Mongo, Pydantic con `strict=True` rechaza ese
valor porque no es una instancia de `Decimal`. `Money` coerciona Decimal128→Decimal
en la lectura y sigue rechazando float/bool (la fuente típica de errores de
redondeo). Los enteros y strings también se rechazan: la API parsea el string a
Decimal ANTES de construir el modelo, y el código de dominio pasa Decimal explícito.
"""

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated

from bson import Decimal128
from pydantic import BeforeValidator

_CENTAVO = Decimal("0.01")


def _coerce_decimal(v: object) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if isinstance(v, Decimal128):  # lo que devuelve BSON/Motor al releer
        return v.to_decimal()
    # bool es subclase de int: hay que descartarlo explícitamente.
    if isinstance(v, bool) or isinstance(v, float):
        raise ValueError("dinero debe ser Decimal, nunca float/bool (regla 1)")
    raise ValueError(
        f"dinero debe ser Decimal (o Decimal128 al leer); recibido {type(v).__name__}"
    )


# Decimal con coerción Decimal128→Decimal en la entrada. Úsese en todo campo COP.
Money = Annotated[Decimal, BeforeValidator(_coerce_decimal)]


def money_str(valor: Decimal) -> str:
    """Serializa un monto COP a string con 2 decimales (contrato de API, regla 1).

    Redondeo bancario HALF_EVEN. Los montos viajan como string en el JSON, nunca
    como número (para no perder precisión en el cliente)."""
    return str(valor.quantize(_CENTAVO, rounding=ROUND_HALF_EVEN))

```

### `backend/app/domain/__init__.py`

```python
# backend/app/domain/__init__.py
"""Modelos de dominio base (Beanie Documents) + registro para init_beanie.

`DOMAIN_DOCUMENTS` es la lista EXPLÍCITA de Documents que se registran en Beanie
(Kimi M-04). `AuditLog`, `User` y `RefreshSession` NO están aquí: sus escrituras van
por repositorios con Motor crudo/conexión dedicada (decisión de la Sesión 2), no por
el ODM general.
"""

from app.domain.configuracion import Configuracion
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro

DOMAIN_DOCUMENTS: list[type] = [Rubro, MesControl, Configuracion]

__all__ = ["Rubro", "MesControl", "Configuracion", "DOMAIN_DOCUMENTS"]

```

### `backend/app/domain/rubro.py`

```python
# backend/app/domain/rubro.py
"""Rubro (Spec §1.2) + semilla real del Excel congelado.

La semilla NO es de juguete: sale de `Flujo de pagos deudas.xlsx` (hoja
'Presupuesto', fuente de verdad del negocio, PRD M1). Son las 31 categorías reales
de RODDOS agrupadas en los 5 grupos + el rubro de sistema 'Ajuste de conciliación'
(que no está en el Excel pero exige el Spec §2.2.6 para el cierre de mes). En total
32 rubros; 2 de sistema ('Por clasificar' y 'Ajuste de conciliación'), inmutables.
"""

from enum import StrEnum

from beanie import Document
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

RUBROS_COLLECTION = "rubros"


class RubroGrupo(StrEnum):
    COSTO_PRODUCTO = "costo_producto"
    OPERACION = "operacion"
    NOMINA = "nomina"
    DEUDAS_OBLIGACIONES = "deudas_obligaciones"
    OTROS = "otros"


class TipoFlujo(StrEnum):
    EGRESO = "egreso"
    INGRESO = "ingreso"


class Rubro(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    grupo: RubroGrupo
    nombre: str = Field(max_length=80)
    tipo_flujo: TipoFlujo = TipoFlujo.EGRESO
    orden: int
    activo: bool = True
    es_sistema: bool = False

    class Settings:
        name = RUBROS_COLLECTION
        # Único por grupo (Spec §1.2). En Mongo real lanza DuplicateKeyError;
        # mongomock no lo exige → se prueba con @requires_real_mongo.
        indexes = [
            IndexModel(
                [("grupo", 1), ("nombre", 1)], name="grupo_nombre_unico", unique=True
            ),
            IndexModel([("orden", 1)], name="por_orden"),
        ]

    @field_validator("grupo", mode="before")
    @classmethod
    def _cast_grupo(cls, v: object) -> object:
        return v if isinstance(v, RubroGrupo) else RubroGrupo(v)

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)


def _seed() -> list[dict]:
    """Catálogo real en el orden de la vista Control del Excel; `orden` global 1..32."""
    G = RubroGrupo
    por_grupo: list[tuple[RubroGrupo, list[str]]] = [
        (G.COSTO_PRODUCTO, ["Producto", "SOAT/Matrículas", "Seguros (Hunter)"]),
        (
            G.OPERACION,
            [
                "Arriendos",
                "Tecnología y software",
                "Mobiliario/planta/equipo",
                "Servicios públicos y telecom",
                "Mercado y aseo",
                "Cafetería",
                "Transporte/peajes/combustible/parqueo",
                "Papelería",
                "Marketing y publicidad",
                "Gastos de representación",
                "Renting",
            ],
        ),
        (
            G.NOMINA,
            [
                "Sueldos empleados",
                "Sueldos directivos",
                "Bonificaciones",
                "Beneficios Heads",
                "Planillas nuevas",
                "Planillas anteriores",
            ],
        ),
        (
            G.DEUDAS_OBLIGACIONES,
            [
                "Préstamos",
                "Deudas tarjetas de crédito",
                "Garantía cupo",
                "Deudas impuestos",
                "Deudas proveedores anteriores",
            ],
        ),
        (
            G.OTROS,
            [
                "Otros gastos",
                "Gastos notariales",
                "Gastos bancarios",
                "Gastos financieros",
                "Impuestos",
                "Por clasificar",  # de sistema (Spec §1.2)
            ],
        ),
    ]
    sistema = {"Por clasificar"}
    filas: list[dict] = []
    orden = 0
    for grupo, nombres in por_grupo:
        for nombre in nombres:
            orden += 1
            filas.append(
                {
                    "grupo": grupo.value,
                    "nombre": nombre,
                    "tipo_flujo": "egreso",
                    "orden": orden,
                    "activo": True,
                    "es_sistema": nombre in sistema,
                }
            )
    # 'Ajuste de conciliación': de sistema, exigido por el cierre (Spec §2.2.6);
    # no vive en el Excel. Grupo 'otros'.
    orden += 1
    filas.append(
        {
            "grupo": G.OTROS.value,
            "nombre": "Ajuste de conciliación",
            "tipo_flujo": "egreso",
            "orden": orden,
            "activo": True,
            "es_sistema": True,
        }
    )
    return filas


SEMILLA_RUBROS: list[dict] = _seed()

```

### `backend/app/domain/mes_control.py`

```python
# backend/app/domain/mes_control.py
"""MesControl (Spec §1.3): el mes de trabajo del ciclo presupuestal.

Decisión (regla 2 de CLAUDE.md): las fechas se guardan como string 'YYYY-MM-DD'
(mes normalizado al día 1), NO como Date. BSON no tiene fecha-sin-hora: un `date`
se persiste como datetime a medianoche y al releer vuelve datetime → romperia el
schema strict y arrastraría zona horaria. El string es inequívoco y estable.
"""

import re
from datetime import datetime
from enum import StrEnum

from beanie import Document
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money

MESES_CONTROL_COLLECTION = "meses_control"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valida_fecha(v: object, *, dia1: bool = False) -> str:
    if not isinstance(v, str) or not _FECHA.match(v):
        raise ValueError("fecha debe ser string 'YYYY-MM-DD'")
    try:
        d = datetime.strptime(v, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"fecha inválida: {v}") from e
    if dia1 and d.day != 1:
        raise ValueError("el mes debe estar normalizado al día 1 (YYYY-MM-01)")
    return v


class EstadoMes(StrEnum):
    SUGERIDO = "sugerido"
    PROPUESTO = "propuesto"
    DEFINIDO = "definido"
    EN_EJECUCION = "en_ejecucion"
    CERRADO = "cerrado"


class MesCerradoError(Exception):
    """Se intentó editar un mes cerrado (histórico inmutable, regla 4)."""


class SaldoBanco(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    banco: str
    saldo: Money
    fecha_reporte: str

    @field_validator("fecha_reporte")
    @classmethod
    def _fecha(cls, v: object) -> str:
        return _valida_fecha(v)


class MesControl(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    mes: str  # 'YYYY-MM-01', llave de negocio (única)
    estado: EstadoMes = EstadoMes.SUGERIDO
    saldo_inicial_caja: Money
    saldos_banco: list[SaldoBanco] = Field(default_factory=list)
    ingresos_esperados_semana: Money | None = None
    definido_por: str | None = None
    definido_at: datetime | None = None
    cerrado_por: str | None = None
    cerrado_at: datetime | None = None

    class Settings:
        name = MESES_CONTROL_COLLECTION
        indexes = [IndexModel([("mes", 1)], name="mes_unico", unique=True)]

    @field_validator("mes")
    @classmethod
    def _mes_dia1(cls, v: object) -> str:
        return _valida_fecha(v, dia1=True)

    @field_validator("estado", mode="before")
    @classmethod
    def _cast_estado(cls, v: object) -> object:
        return v if isinstance(v, EstadoMes) else EstadoMes(v)

    @field_validator("definido_at", "cerrado_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v

    def assert_editable(self) -> None:
        """Los meses cerrados son inmutables (regla 4). Las tardías (tardia=true)
        son la única excepción y se manejan en el flujo de cierre (Sprint 4)."""
        if self.estado is EstadoMes.CERRADO:
            raise MesCerradoError(f"el mes {self.mes} está cerrado y es inmutable")

```

### `backend/app/domain/configuracion.py`

```python
# backend/app/domain/configuracion.py
"""Configuracion (Spec §1.10): reglas de negocio parametrizables en BD, no en env.

`valor` polimórfico TIPADO POR CLAVE (Kimi M-03): en vez de un `valor` genérico que
rompería 'dinero=Decimal', cada clave declara su tipo esperado y se persiste en el
campo correspondiente (`valor_decimal` COP, `valor_fecha` 'YYYY-MM-DD', `valor_json`).
Exactamente uno de los tres va poblado, y debe coincidir con el tipo de la clave.
"""

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from beanie import Document
from pydantic import ConfigDict, field_validator, model_validator
from pymongo import IndexModel

from app.core.money import Money

CONFIGURACION_COLLECTION = "configuracion"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ClaveConfig(StrEnum):
    UMBRAL_DIF_BANCO_CIERRE = "UMBRAL_DIF_BANCO_CIERRE"
    CALENDARIO_DIAN = "CALENDARIO_DIAN"
    DIAS_CREDITO_POR_PROVEEDOR = "DIAS_CREDITO_POR_PROVEEDOR"


# Tipo esperado por clave (M-03). "decimal" | "fecha" | "json".
_TIPO_POR_CLAVE: dict[ClaveConfig, str] = {
    ClaveConfig.UMBRAL_DIF_BANCO_CIERRE: "decimal",
    ClaveConfig.CALENDARIO_DIAN: "json",
    ClaveConfig.DIAS_CREDITO_POR_PROVEEDOR: "json",
}


class Configuracion(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    clave: ClaveConfig
    valor_decimal: Money | None = None
    valor_fecha: str | None = None
    valor_json: dict[str, Any] | None = None
    vigente_desde: str  # 'YYYY-MM-DD'
    modificado_por: str | None = None

    class Settings:
        name = CONFIGURACION_COLLECTION
        # Historial temporal: una fila por (clave, vigente_desde).
        indexes = [
            IndexModel(
                [("clave", 1), ("vigente_desde", 1)],
                name="clave_vigencia_unica",
                unique=True,
            )
        ]

    @field_validator("clave", mode="before")
    @classmethod
    def _cast_clave(cls, v: object) -> object:
        return v if isinstance(v, ClaveConfig) else ClaveConfig(v)

    @field_validator("vigente_desde", "valor_fecha")
    @classmethod
    def _fecha(cls, v: object) -> object:
        if v is None:
            return v
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("fecha debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha inválida: {v}") from e
        return v

    @model_validator(mode="after")
    def _un_solo_valor_del_tipo_correcto(self) -> "Configuracion":
        presentes = {
            "decimal": self.valor_decimal is not None,
            "fecha": self.valor_fecha is not None,
            "json": self.valor_json is not None,
        }
        cuantos = sum(presentes.values())
        if cuantos != 1:
            raise ValueError(
                f"debe poblarse exactamente un valor_* (recibidos: {cuantos})"
            )
        esperado = _TIPO_POR_CLAVE[self.clave]
        if not presentes[esperado]:
            raise ValueError(
                f"la clave {self.clave.value} exige valor_{esperado} (M-03)"
            )
        return self


# --- Semilla real (fechas IVA de RODDOS, NIT 901012622 dígito 2) ---
# ene–abr → 13-may-26 · may–ago → 10-sep-26 · sep–dic → 14-ene-27
SEMILLA_CONFIGURACION: list[dict] = [
    {
        "clave": "UMBRAL_DIF_BANCO_CIERRE",
        "valor_decimal": Decimal("50000"),  # Spec §0.1 (default, editable por Admin)
        "vigente_desde": "2026-01-01",
    },
    {
        "clave": "CALENDARIO_DIAN",
        "valor_json": {
            "2026": {
                "ene_abr": "2026-05-13",
                "may_ago": "2026-09-10",
                "sep_dic": "2027-01-14",
            }
        },
        "vigente_desde": "2026-01-01",
    },
    {
        # Días de crédito por proveedor: dato operativo que administra Financiero;
        # se declara la clave con dict vacío (no se inventan valores).
        "clave": "DIAS_CREDITO_POR_PROVEEDOR",
        "valor_json": {},
        "vigente_desde": "2026-01-01",
    },
]

```

### `backend/app/domain/seed.py`

```python
# backend/app/domain/seed.py
"""Semillas idempotentes de dominio (rubros y configuración).

Idempotencia por `$setOnInsert` sobre la llave de negocio: una segunda corrida NO
duplica ni sobreescribe ediciones posteriores del Admin. Devuelven cuántos docs
NUEVOS insertaron. Operan sobre una database Motor ya inicializada por Beanie.
"""

from decimal import Decimal
from typing import Any

from bson import Decimal128

from app.domain.configuracion import (
    CONFIGURACION_COLLECTION,
    SEMILLA_CONFIGURACION,
)
from app.domain.rubro import RUBROS_COLLECTION, SEMILLA_RUBROS


def _a_bson(v: Any) -> Any:
    """Escribimos por Motor crudo (no por el ODM), así que pymongo NO encodea
    `Decimal` — hay que pasarlo como `Decimal128` (regla 1; al leer, el tipo Money
    lo devuelve a Decimal)."""
    if isinstance(v, Decimal):
        return Decimal128(v)
    if isinstance(v, dict):
        return {k: _a_bson(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_a_bson(x) for x in v]
    return v


async def _upsert_muchos(
    db: Any, coleccion: str, filas: list[dict], llave: list[str]
) -> int:
    insertados = 0
    col = db[coleccion]
    for fila in filas:
        filtro = {k: fila[k] for k in llave}
        doc = _a_bson(fila)
        res = await col.update_one(filtro, {"$setOnInsert": doc}, upsert=True)
        if res.upserted_id is not None:
            insertados += 1
    return insertados


async def seed_rubros(db: Any) -> int:
    """Inserta las 32 categorías reales (idempotente por (grupo, nombre))."""
    return await _upsert_muchos(
        db, RUBROS_COLLECTION, SEMILLA_RUBROS, ["grupo", "nombre"]
    )


async def seed_configuracion(db: Any) -> int:
    """Inserta las claves iniciales (idempotente por (clave, vigente_desde))."""
    return await _upsert_muchos(
        db, CONFIGURACION_COLLECTION, SEMILLA_CONFIGURACION, ["clave", "vigente_desde"]
    )

```

## 6. Diffs de archivos modificados

### diff `backend/app/db/mongo.py`

```diff
diff --git a/backend/app/db/mongo.py b/backend/app/db/mongo.py
index abb1eee..fd2e9cf 100644
--- a/backend/app/db/mongo.py
+++ b/backend/app/db/mongo.py
@@ -1,14 +1,16 @@
 # backend/app/db/mongo.py
 """Conexión a MongoDB (Motor) e inicialización de Beanie.
 
-Sprint 0, Sesión 1: dejamos el plumbing listo y probado, pero SIN registrar
-document models todavía (no existen). `init_beanie_for` se probará contra
-mongomock y se cableará en el lifespan del web en el Sprint 0b, cuando lleguen
-los primeros modelos (Rubro, MesControl, Configuracion, AuditLog...).
+Sprint 0b: se registran los primeros Documents de dominio (Rubro, MesControl,
+Configuracion) y se cablea `init_beanie` en el lifespan. `AuditLog`, `User` y
+`RefreshSession` NO son Documents de Beanie: sus escrituras van por Motor crudo
+(conexión dedicada de auditoría / repositorios de auth), decisión de la Sesión 2.
 
 Diseño consciente: el cliente Motor se crea de forma perezosa (no conecta
 hasta el primer comando), por eso el servicio web arranca aunque Mongo esté
-caído — la liveness (/health) no depende de la BD; la readiness sí.
+caído — la liveness (/health) no depende de la BD; la readiness sí. Como
+`init_beanie` sí conecta (crea índices), en el lifespan se llama de forma NO
+fatal y se reintenta desde readiness (ver app.main), preservando esa garantía.
 """
 
 from typing import Any
@@ -16,10 +18,11 @@ from typing import Any
 from beanie import init_beanie
 from motor.motor_asyncio import AsyncIOMotorClient
 
-# Document models de Beanie (para lecturas), se poblará cuando existan Documents.
-# AuditLog NO va aquí: es un Pydantic plano y sus escrituras van por la conexión
-# dedicada `compas_audit` (app.audit.service), no por el ODM general.
-DOCUMENT_MODELS: list[type] = []
+from app.domain import DOMAIN_DOCUMENTS
+
+# Document models de Beanie. Fuente única: el registro explícito de app.domain
+# (Kimi M-04). AuditLog/User/RefreshSession NO van aquí (Motor crudo).
+DOCUMENT_MODELS: list[type] = DOMAIN_DOCUMENTS
 
 
 def create_client(uri: str) -> AsyncIOMotorClient:
@@ -27,12 +30,12 @@ def create_client(uri: str) -> AsyncIOMotorClient:
     return AsyncIOMotorClient(uri, tz_aware=True)
 
 
-async def init_beanie_for(client: Any, db_name: str) -> None:
-    """Inicializa Beanie sobre la database indicada.
-
-    En la Sesión 1 `DOCUMENT_MODELS` está vacío; se irá llenando por sprint.
-    """
-    await init_beanie(database=client[db_name], document_models=DOCUMENT_MODELS)
+async def init_beanie_for(
+    client: Any, db_name: str, document_models: list[type] | None = None
+) -> None:
+    """Inicializa Beanie sobre la database indicada con los Documents de dominio."""
+    models = DOCUMENT_MODELS if document_models is None else document_models
+    await init_beanie(database=client[db_name], document_models=models)
 
 
 async def ping(client: Any) -> None:

```

### diff `backend/app/main.py`

```diff
diff --git a/backend/app/main.py b/backend/app/main.py
index f49fb14..553043a 100644
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -61,6 +61,22 @@ def _init_sentry(settings) -> None:
     )
 
 
+async def ensure_beanie(app: FastAPI, client, db_name: str) -> bool:
+    """Inicializa Beanie una sola vez (idempotente). NO fatal: si Mongo está caído
+    devuelve False y deja `app.state.beanie_ready=False`, sin tumbar la liveness.
+    Readiness lo reintenta hasta que la BD responda."""
+    if getattr(app.state, "beanie_ready", False):
+        return True
+    try:
+        await mongo.init_beanie_for(client, db_name)
+        app.state.beanie_ready = True
+        return True
+    except Exception:  # noqa: BLE001 — degradación controlada, no crash de startup
+        logger.warning("init_beanie falló (Mongo no disponible aún); se reintentará.")
+        app.state.beanie_ready = False
+        return False
+
+
 @asynccontextmanager
 async def lifespan(app: FastAPI):
     settings = get_settings()
@@ -90,8 +106,12 @@ async def lifespan(app: FastAPI):
     client = mongo.create_client(settings.mongodb_uri_compas)
     app.state.mongo_client = client
     app.state.settings = settings
-    # NOTA (Sprint 0b): cuando existan document models, llamar aquí
-    #   await mongo.init_beanie_for(client, settings.mongodb_db)
+    app.state.beanie_ready = False
+
+    # init_beanie SÍ conecta (crea índices) → si Mongo está caído al arrancar,
+    # colgaría/reventaría el startup y romperia la garantía "liveness sin BD".
+    # Por eso es NO fatal aquí y se reintenta idempotentemente desde readiness.
+    await ensure_beanie(app, client, settings.mongodb_db)
 
     # Conexión DEDICADA de auditoría (DoD #6). MONGODB_URI_AUDIT usa el usuario
     # `compas_audit` (audit_writer). FAIL-FAST fuera de dev (Kimi C-01): un warning

```

### diff `backend/app/api/v1/health.py`

```diff
diff --git a/backend/app/api/v1/health.py b/backend/app/api/v1/health.py
index 8d21c1c..0d129d3 100644
--- a/backend/app/api/v1/health.py
+++ b/backend/app/api/v1/health.py
@@ -6,7 +6,7 @@ healthCheckPath de render.yaml y no debe colgar de la API v1."""
 
 from typing import Any
 
-from fastapi import APIRouter, Depends, Response
+from fastapi import APIRouter, Depends, Request, Response
 
 from app.db import mongo
 from app.deps import get_mongo_client
@@ -15,11 +15,27 @@ router = APIRouter(tags=["health"])
 
 
 @router.get("/health/ready")
-async def readiness(response: Response, client: Any = Depends(get_mongo_client)):
-    """503 si Mongo no responde; 200 con {status: ready} si el ping funciona."""
+async def readiness(
+    request: Request, response: Response, client: Any = Depends(get_mongo_client)
+):
+    """503 si Mongo no responde; 200 con {status: ready} si el ping funciona.
+
+    Aprovecha el ping (Mongo arriba) para reintentar `init_beanie` si el arranque
+    ocurrió con la BD caída (init no fatal en el lifespan)."""
     try:
         await mongo.ping(client)
     except Exception:
         response.status_code = 503
         return {"status": "not_ready", "mongo": "down"}
-    return {"status": "ready", "mongo": "up"}
+
+    # Mongo respondió: si Beanie no quedó inicializado en el arranque, reintentar.
+    from app.main import ensure_beanie
+
+    app = request.app
+    if not getattr(app.state, "beanie_ready", False):
+        await ensure_beanie(app, app.state.mongo_client, app.state.settings.mongodb_db)
+    return {
+        "status": "ready",
+        "mongo": "up",
+        "beanie": "ready" if app.state.beanie_ready else "pending",
+    }

```

### diff `backend/tests/conftest.py`

```diff
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
index 8255484..838b6fb 100644
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -59,6 +59,27 @@ def pytest_collection_modifyitems(
             item.add_marker(skip)
 
 
+@pytest.fixture(autouse=True, scope="session")
+def _beanie_documents_initialized():
+    """Beanie 2.0 no permite INSTANCIAR un Document sin init_beanie previo. Los
+    tests unitarios de dominio (construcción/validación, sin I/O) necesitan las
+    clases inicializadas. Lo hacemos una vez por sesión contra mongomock; los
+    tests de persistencia re-inicializan con su propia BD dentro de su event loop."""
+    import asyncio
+
+    from app.domain import DOMAIN_DOCUMENTS
+    from beanie import init_beanie
+
+    async def _do() -> None:
+        client = AsyncMongoMockClient()
+        await init_beanie(
+            database=client["compas_construct"], document_models=DOMAIN_DOCUMENTS
+        )
+
+    asyncio.run(_do())
+    yield
+
+
 @pytest.fixture(autouse=True)
 def _clear_settings_cache():
     """Limpia el cache de get_settings antes y después de cada test — evita que un
@@ -77,15 +98,20 @@ def mock_mongo_client() -> AsyncMongoMockClient:
 
 
 @pytest.fixture
-def app(mock_mongo_client: AsyncMongoMockClient):
+def app(mock_mongo_client: AsyncMongoMockClient, monkeypatch: pytest.MonkeyPatch):
     """App FastAPI con el cliente Mongo real reemplazado por el mock.
 
     RUN_SCHEDULER queda en false (default): el servicio web NUNCA arranca el
-    scheduler (regla 6 de CLAUDE.md)."""
+    scheduler (regla 6 de CLAUDE.md).
+
+    El lifespan ahora llama `init_beanie` (Sprint 0b): parcheamos `create_client`
+    para que use el mock, no un cliente real que colgaría al intentar conectar."""
     from app.config import get_settings
+    from app.db import mongo
 
     os.environ.pop("RUN_SCHEDULER", None)
     get_settings.cache_clear()
+    monkeypatch.setattr(mongo, "create_client", lambda _uri: mock_mongo_client)
     application = create_app()
     application.dependency_overrides[get_mongo_client] = lambda: mock_mongo_client
     return application

```

### diff `backend/tests/test_db.py`

```diff
diff --git a/backend/tests/test_db.py b/backend/tests/test_db.py
index cd7600f..f025980 100644
--- a/backend/tests/test_db.py
+++ b/backend/tests/test_db.py
@@ -11,9 +11,14 @@ async def test_ping_ok_con_mongomock():
     await mongo.ping(client)
 
 
-async def test_init_beanie_sin_modelos_no_falla():
-    """DOCUMENT_MODELS aún vacío (AuditLog es Pydantic plano, no Beanie Document);
-    init_beanie debe ser un no-op seguro."""
+async def test_init_beanie_registra_los_documents_de_dominio():
+    """Sprint 0b: DOCUMENT_MODELS = los 3 Documents de dominio (Kimi M-04).
+    AuditLog/User/RefreshSession NO están (Motor crudo)."""
+    from app.audit.models import AuditLog
+    from app.domain import DOMAIN_DOCUMENTS
+
+    assert mongo.DOCUMENT_MODELS == DOMAIN_DOCUMENTS
+    assert len(DOMAIN_DOCUMENTS) == 3
+    assert AuditLog not in mongo.DOCUMENT_MODELS
     client = AsyncMongoMockClient()
-    assert mongo.DOCUMENT_MODELS == []
-    await mongo.init_beanie_for(client, "compas_test")
+    await mongo.init_beanie_for(client, "compas_test")  # no debe lanzar

```

## 7. Tests nuevos

### `backend/tests/test_domain_money.py`

```python
# backend/tests/test_domain_money.py
"""Tipo Money: Decimal end-to-end, jamás float (regla 1 de CLAUDE.md).

BSON persiste Decimal como Decimal128; al releer, Pydantic strict lo rechaza
salvo que lo coercionemos a Decimal. Este tipo es la defensa: acepta Decimal y
Decimal128, y RECHAZA float/bool (la fuente típica de errores de redondeo)."""

from decimal import Decimal

import pytest
from app.core.money import Money, money_str
from bson import Decimal128
from pydantic import BaseModel, ConfigDict, ValidationError


class _M(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    v: Money


def test_acepta_decimal():
    assert _M(v=Decimal("1234567.89")).v == Decimal("1234567.89")


def test_acepta_decimal128_de_mongo():
    # Lo que devuelve BSON/Motor al releer un Decimal.
    m = _M(v=Decimal128("50000.00"))
    assert isinstance(m.v, Decimal)
    assert m.v == Decimal("50000.00")


@pytest.mark.parametrize("malo", [1234.5, 0.1, True, False])
def test_rechaza_float_y_bool(malo):
    with pytest.raises(ValidationError):
        _M(v=malo)


@pytest.mark.parametrize("malo", ["1000", 1000, None])
def test_rechaza_str_int_none(malo):
    # Forzamos a los llamadores a pasar Decimal explícito (la API parsea el
    # string a Decimal ANTES de construir el modelo).
    with pytest.raises(ValidationError):
        _M(v=malo)


def test_money_str_dos_decimales():
    assert money_str(Decimal("50000")) == "50000.00"
    assert money_str(Decimal("1234567.891")) == "1234567.89"  # HALF_EVEN

```

### `backend/tests/test_domain_rubro.py`

```python
# backend/tests/test_domain_rubro.py
"""Rubro (Spec §1.2) + semilla real del Excel congelado (PRD M1, Kimi M-02)."""


import pytest
from app.domain.rubro import (
    SEMILLA_RUBROS,
    Rubro,
    RubroGrupo,
    TipoFlujo,
)
from pydantic import ValidationError

GRUPOS = {
    "costo_producto",
    "operacion",
    "nomina",
    "deudas_obligaciones",
    "otros",
}


def test_grupos_son_los_cinco_del_prd():
    assert {g.value for g in RubroGrupo} == GRUPOS


def test_rubro_valido():
    r = Rubro(grupo="operacion", nombre="Arriendos", tipo_flujo="egreso", orden=4)
    assert r.grupo is RubroGrupo.OPERACION
    assert r.tipo_flujo is TipoFlujo.EGRESO
    assert r.activo is True and r.es_sistema is False


def test_strict_rechaza_campo_extra():
    with pytest.raises(ValidationError):
        Rubro(grupo="otros", nombre="X", orden=1, inventado=1)


def test_nombre_max_80():
    with pytest.raises(ValidationError):
        Rubro(grupo="otros", nombre="x" * 81, orden=1)


# ---- Semilla real (frozen: Flujo de pagos deudas.xlsx, hoja 'Presupuesto') ----


def test_semilla_tiene_32_rubros():
    # 31 categorías del Excel + 'Ajuste de conciliación' (de sistema, Spec §2.2.6)
    assert len(SEMILLA_RUBROS) == 32


def test_semilla_cubre_los_cinco_grupos():
    assert {r["grupo"] for r in SEMILLA_RUBROS} == GRUPOS


def test_semilla_dos_rubros_de_sistema():
    sistema = [r["nombre"] for r in SEMILLA_RUBROS if r["es_sistema"]]
    assert set(sistema) == {"Por clasificar", "Ajuste de conciliación"}


def test_semilla_todos_egreso():
    assert all(r["tipo_flujo"] == "egreso" for r in SEMILLA_RUBROS)


def test_semilla_nombres_unicos_por_grupo():
    vistos = set()
    for r in SEMILLA_RUBROS:
        clave = (r["grupo"], r["nombre"])
        assert clave not in vistos, f"duplicado {clave}"
        vistos.add(clave)


def test_semilla_ordenes_unicos_y_consecutivos():
    ordenes = sorted(r["orden"] for r in SEMILLA_RUBROS)
    assert ordenes == list(range(1, 33))


def test_semilla_construye_modelos_validos():
    for r in SEMILLA_RUBROS:
        Rubro(**r)  # no debe lanzar


def test_semilla_incluye_categorias_reales_conocidas():
    nombres = {r["nombre"] for r in SEMILLA_RUBROS}
    for esperado in (
        "Producto",
        "SOAT/Matrículas",
        "Seguros (Hunter)",
        "Transporte/peajes/combustible/parqueo",
        "Sueldos directivos",
        "Préstamos",
        "Impuestos",
    ):
        assert esperado in nombres, esperado

```

### `backend/tests/test_domain_mes_control.py`

```python
# backend/tests/test_domain_mes_control.py
"""MesControl (Spec §1.3): mes normalizado al día 1, estados, saldos Decimal,
inmutabilidad de meses cerrados (regla 4 de CLAUDE.md)."""

from decimal import Decimal

import pytest
from app.domain.mes_control import (
    EstadoMes,
    MesCerradoError,
    MesControl,
    SaldoBanco,
)
from pydantic import ValidationError


def test_mes_valido():
    m = MesControl(mes="2026-07-01", saldo_inicial_caja=Decimal("675967053.19"))
    assert m.estado is EstadoMes.SUGERIDO  # default
    assert m.saldo_inicial_caja == Decimal("675967053.19")


@pytest.mark.parametrize("malo", ["2026-07-15", "2026-7-1", "2026/07/01", "julio"])
def test_mes_debe_ser_primer_dia_formato_estricto(malo):
    with pytest.raises(ValidationError):
        MesControl(mes=malo, saldo_inicial_caja=Decimal("0"))


def test_saldo_no_admite_float():
    with pytest.raises(ValidationError):
        MesControl(mes="2026-07-01", saldo_inicial_caja=675967053.19)


def test_saldos_banco():
    m = MesControl(
        mes="2026-07-01",
        saldo_inicial_caja=Decimal("0"),
        saldos_banco=[
            SaldoBanco(
                banco="Bancolombia", saldo=Decimal("100.00"), fecha_reporte="2026-07-31"
            )
        ],
    )
    assert m.saldos_banco[0].banco == "Bancolombia"


def test_estado_enum_completo():
    assert {e.value for e in EstadoMes} == {
        "sugerido",
        "propuesto",
        "definido",
        "en_ejecucion",
        "cerrado",
    }


def test_mes_cerrado_es_inmutable():
    m = MesControl(mes="2026-06-01", estado="cerrado", saldo_inicial_caja=Decimal("0"))
    with pytest.raises(MesCerradoError):
        m.assert_editable()


def test_mes_abierto_es_editable():
    m = MesControl(
        mes="2026-07-01", estado="en_ejecucion", saldo_inicial_caja=Decimal("0")
    )
    m.assert_editable()  # no lanza

```

### `backend/tests/test_domain_configuracion.py`

```python
# backend/tests/test_domain_configuracion.py
"""Configuracion (Spec §1.10): valor tipado por clave (Kimi M-03) + semilla real.

CALENDARIO_DIAN con las fechas REALES de RODDOS (NIT 901012622, dígito 2):
ene–abr → 13-may-26, may–ago → 10-sep-26, sep–dic → 14-ene-27."""

from decimal import Decimal

import pytest
from app.domain.configuracion import (
    SEMILLA_CONFIGURACION,
    Configuracion,
)
from pydantic import ValidationError


def test_umbral_es_decimal():
    c = Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    )
    assert c.valor_decimal == Decimal("50000")


def test_calendario_es_json():
    c = Configuracion(
        clave="CALENDARIO_DIAN",
        valor_json={"2026": {"may_ago": "2026-09-10"}},
        vigente_desde="2026-01-01",
    )
    assert c.valor_json["2026"]["may_ago"] == "2026-09-10"


def test_exactamente_un_valor():
    # cero valores -> error
    with pytest.raises(ValidationError):
        Configuracion(clave="UMBRAL_DIF_BANCO_CIERRE", vigente_desde="2026-01-01")
    # dos valores -> error
    with pytest.raises(ValidationError):
        Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=Decimal("1"),
            valor_json={"x": 1},
            vigente_desde="2026-01-01",
        )


def test_tipo_debe_coincidir_con_la_clave():
    # UMBRAL_DIF_BANCO_CIERRE es Decimal: pasarle json debe fallar (M-03)
    with pytest.raises(ValidationError):
        Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_json={"x": 1},
            vigente_desde="2026-01-01",
        )


def test_umbral_no_admite_float():
    with pytest.raises(ValidationError):
        Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=50000.0,
            vigente_desde="2026-01-01",
        )


# ---- Semilla ----


def test_semilla_tiene_las_tres_claves():
    claves = {c["clave"] for c in SEMILLA_CONFIGURACION}
    assert claves == {
        "UMBRAL_DIF_BANCO_CIERRE",
        "CALENDARIO_DIAN",
        "DIAS_CREDITO_POR_PROVEEDOR",
    }


def test_semilla_umbral_50000():
    umbral = next(
        c for c in SEMILLA_CONFIGURACION if c["clave"] == "UMBRAL_DIF_BANCO_CIERRE"
    )
    assert umbral["valor_decimal"] == Decimal("50000")


def test_semilla_calendario_dian_fechas_reales():
    cal = next(c for c in SEMILLA_CONFIGURACION if c["clave"] == "CALENDARIO_DIAN")
    v = cal["valor_json"]["2026"]
    assert v["ene_abr"] == "2026-05-13"
    assert v["may_ago"] == "2026-09-10"
    assert v["sep_dic"] == "2027-01-14"


def test_semilla_construye_modelos_validos():
    for c in SEMILLA_CONFIGURACION:
        Configuracion(**c)

```

### `backend/tests/test_domain_persistence.py`

```python
# backend/tests/test_domain_persistence.py
"""Round-trip contra Beanie+mongomock: Decimal sobrevive (Decimal128→Decimal) y
la semilla es idempotente. La UNICIDAD de índices NO se prueba aquí (mongomock no
la exige) — eso está en test_domain_indexes.py con @requires_real_mongo."""

from decimal import Decimal

import pytest
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.seed import seed_configuracion, seed_rubros
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
async def db():
    client = AsyncMongoMockClient()
    database = client["compas_test"]
    await init_beanie(database=database, document_models=DOMAIN_DOCUMENTS)
    return database


async def test_rubro_round_trip(db):
    await Rubro(grupo="operacion", nombre="Arriendos", orden=4).insert()
    got = await Rubro.find_one(Rubro.nombre == "Arriendos")
    assert got is not None and got.grupo.value == "operacion"


async def test_mes_control_decimal_round_trip(db):
    await MesControl(
        mes="2026-07-01", saldo_inicial_caja=Decimal("675967053.19")
    ).insert()
    got = await MesControl.find_one(MesControl.mes == "2026-07-01")
    assert isinstance(got.saldo_inicial_caja, Decimal)
    assert got.saldo_inicial_caja == Decimal("675967053.19")


async def test_configuracion_decimal_round_trip(db):
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    ).insert()
    got = await Configuracion.find_one(Configuracion.clave == "UMBRAL_DIF_BANCO_CIERRE")
    assert got.valor_decimal == Decimal("50000")


async def test_seed_rubros_idempotente(db):
    n1 = await seed_rubros(db)
    total1 = await Rubro.find_all().count()
    n2 = await seed_rubros(db)  # segunda corrida: no debe duplicar
    total2 = await Rubro.find_all().count()
    assert n1 == 32 and total1 == 32
    assert n2 == 0 and total2 == 32
    sistema = await Rubro.find(Rubro.es_sistema == True).count()  # noqa: E712
    assert sistema == 2


async def test_seed_configuracion_idempotente(db):
    await seed_configuracion(db)
    await seed_configuracion(db)
    total = await Configuracion.find_all().count()
    assert total == 3

```

### `backend/tests/test_domain_indexes.py`

```python
# backend/tests/test_domain_indexes.py
"""Unicidad de índices — SOLO contra Mongo REAL (mongomock no la exige).

Correr con:  pytest -m requires_real_mongo  (COMPAS_TEST_MONGO_URI apuntando a
un mongod real). En CI de la Sesión 3 (prerrequisito duro del Gate G1)."""

import os
from decimal import Decimal

import pytest
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.rubro import Rubro
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

pytestmark = pytest.mark.requires_real_mongo


@pytest.fixture
async def real_db():
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    dbname = "compas_test_idx"
    await client.drop_database(dbname)
    database = client[dbname]
    await init_beanie(database=database, document_models=DOMAIN_DOCUMENTS)
    yield database
    await client.drop_database(dbname)
    client.close()


async def test_rubro_nombre_unico_por_grupo(real_db):
    await Rubro(grupo="operacion", nombre="Arriendos", orden=1).insert()
    with pytest.raises(DuplicateKeyError):
        await Rubro(grupo="operacion", nombre="Arriendos", orden=2).insert()


async def test_mismo_nombre_distinto_grupo_ok(real_db):
    await Rubro(grupo="operacion", nombre="Impuestos", orden=1).insert()
    await Rubro(grupo="otros", nombre="Impuestos", orden=2).insert()  # no colisiona


async def test_configuracion_clave_vigencia_unica(real_db):
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    ).insert()
    with pytest.raises(DuplicateKeyError):
        await Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=Decimal("60000"),
            vigente_desde="2026-01-01",
        ).insert()

```

### `backend/tests/test_init_beanie_wiring.py`

```python
# backend/tests/test_init_beanie_wiring.py
"""init_beanie cableado en el lifespan SIN romper 'liveness sin BD'.

`init_beanie` conecta (crea índices). Si Mongo está caído al arrancar, el startup
NO debe caerse: /health sigue en 200 y Beanie se reintenta desde readiness."""

from fastapi.testclient import TestClient


def test_beanie_listo_tras_arranque_normal(app):
    with TestClient(app) as client:
        assert app.state.beanie_ready is True
        r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["beanie"] == "ready"


def test_liveness_sobrevive_si_init_beanie_falla(app, monkeypatch):
    """Mongo caído al arrancar → init_beanie revienta, pero /health responde 200."""
    from app.db import mongo

    async def _revienta(*_a, **_k):
        raise RuntimeError("Mongo caído")

    monkeypatch.setattr(mongo, "init_beanie_for", _revienta)

    with TestClient(app) as client:
        assert app.state.beanie_ready is False  # no se cayó el startup
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readiness_reintenta_beanie(app, monkeypatch):
    """Arranca con init fallando; cuando Mongo 'vuelve', readiness reinicializa."""
    from app.db import mongo

    real_init = mongo.init_beanie_for
    estado = {"falla": True}

    async def _condicional(*a, **k):
        if estado["falla"]:
            raise RuntimeError("Mongo caído")
        await real_init(*a, **k)

    monkeypatch.setattr(mongo, "init_beanie_for", _condicional)

    with TestClient(app) as client:
        assert app.state.beanie_ready is False
        estado["falla"] = False  # Mongo se recupera
        r = client.get("/api/v1/health/ready")
        assert r.status_code == 200
        assert r.json()["beanie"] == "ready"
        assert app.state.beanie_ready is True

```

## 8. Migraciones idempotentes

### `migrations/20260901_seed_rubros.py`

```python
#!/usr/bin/env python
"""Migración idempotente: semilla del catálogo de rubros (Spec §1.2, PRD M1).

Inserta las 32 categorías reales del Excel congelado + el rubro de sistema
'Ajuste de conciliación'. Idempotente ($setOnInsert por (grupo, nombre)): re-correr
no duplica ni pisa ediciones del Admin.

Uso:  python migrations/20260901_seed_rubros.py "<MONGODB_URI>" [db=compas]
Lo corre el operador (RUNBOOK) y el CI de la Sesión 3.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.seed import seed_rubros  # noqa: E402


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    n = await seed_rubros(client[db_name])
    print(f"[rubros] {n} nuevos insertados (idempotente).")
    client.close()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Uso: python migrations/20260901_seed_rubros.py "<MONGODB_URI>" [db]')
    uri = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()

```

### `migrations/20260901_seed_configuracion.py`

```python
#!/usr/bin/env python
"""Migración idempotente: claves iniciales de Configuracion (Spec §1.10).

UMBRAL_DIF_BANCO_CIERRE ($50.000), CALENDARIO_DIAN (vencimientos IVA reales de
RODDOS) y DIAS_CREDITO_POR_PROVEEDOR (dict vacío, lo puebla Financiero).
Idempotente ($setOnInsert por (clave, vigente_desde)).

Uso:  python migrations/20260901_seed_configuracion.py "<MONGODB_URI>" [db=compas]
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.seed import seed_configuracion  # noqa: E402


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    n = await seed_configuracion(client[db_name])
    print(f"[configuracion] {n} nuevas insertadas (idempotente).")
    client.close()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(
            'Uso: python migrations/20260901_seed_configuracion.py "<MONGODB_URI>" [db]'
        )
    uri = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()

```
