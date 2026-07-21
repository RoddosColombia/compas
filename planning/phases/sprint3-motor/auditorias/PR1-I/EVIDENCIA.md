# EVIDENCIA — sprint3-motor · PR1-I (motor del sugerido)

Rama `feat/motor-sugerido`, commit `78a7fe8` (SIN mergear).

## 1. pytest
```
270 passed, 23 skipped (16 nuevos: test_motor_sugerido 8 + test_presupuesto_generar 8)
```

## 2. ruff
```
check: All checks passed! · format: limpio
```

## 3. Protocolo
```
r1:0 | journal-entries:0 | estado-pending:0
```

## 4. git diff --stat (main..78a7fe8)
```
backend/app/api/v1/__init__.py            |   2 +
 backend/app/domain/__init__.py            |   3 +
 backend/app/domain/presupuesto.py         |  90 ++++++++++++++
 backend/app/presupuesto/__init__.py       |   4 +
 backend/app/presupuesto/motor.py          |  62 ++++++++++
 backend/app/presupuesto/router.py         |  94 +++++++++++++++
 backend/app/presupuesto/service.py        |  95 +++++++++++++++
 backend/tests/test_db.py                  |   2 +-
 backend/tests/test_motor_sugerido.py      |  97 +++++++++++++++
 backend/tests/test_presupuesto_generar.py | 189 ++++++++++++++++++++++++++++++
 10 files changed, 637 insertions(+), 1 deletion(-)
```

## 5. Diff completo
```diff
diff --git a/backend/app/api/v1/__init__.py b/backend/app/api/v1/__init__.py
index bf6fe43..2f842d2 100644
--- a/backend/app/api/v1/__init__.py
+++ b/backend/app/api/v1/__init__.py
@@ -7,6 +7,7 @@ from app.api.v1 import health
 from app.auth.router import router as auth_router
 from app.cargas.router import router as cargas_router
 from app.ciclo.router import router as ciclo_router
+from app.presupuesto.router import router as presupuesto_router
 from app.transacciones.router import router as transacciones_router
 
 api_router = APIRouter()
@@ -14,4 +15,5 @@ api_router.include_router(health.router)
 api_router.include_router(auth_router)
 api_router.include_router(cargas_router)
 api_router.include_router(ciclo_router)
+api_router.include_router(presupuesto_router)
 api_router.include_router(transacciones_router)
diff --git a/backend/app/domain/__init__.py b/backend/app/domain/__init__.py
index 6022dea..9e40c59 100644
--- a/backend/app/domain/__init__.py
+++ b/backend/app/domain/__init__.py
@@ -11,6 +11,7 @@ from app.domain.carga import CargaBancaria
 from app.domain.configuracion import Configuracion
 from app.domain.idempotency import IdempotencyKey
 from app.domain.mes_control import MesControl
+from app.domain.presupuesto import PresupuestoLinea
 from app.domain.rubro import Rubro
 from app.domain.transaccion import Transaccion
 
@@ -21,6 +22,7 @@ DOMAIN_DOCUMENTS: list[type] = [
     Transaccion,
     CargaBancaria,
     IdempotencyKey,
+    PresupuestoLinea,
 ]
 
 __all__ = [
@@ -30,5 +32,6 @@ __all__ = [
     "Transaccion",
     "CargaBancaria",
     "IdempotencyKey",
+    "PresupuestoLinea",
     "DOMAIN_DOCUMENTS",
 ]
diff --git a/backend/app/domain/presupuesto.py b/backend/app/domain/presupuesto.py
new file mode 100644
index 0000000..f381eef
--- /dev/null
+++ b/backend/app/domain/presupuesto.py
@@ -0,0 +1,90 @@
+# backend/app/domain/presupuesto.py
+"""PresupuestoLinea (Spec §1.4, F-06/F-07): la línea de presupuesto por (mes, rubro).
+
+El sugerido lo calcula el motor §1.4.1; aquí se PERSISTE con sus componentes
+(`prom_3m`, `tendencia_mes`, `crec_pct`) para verificación celda a celda. Versionado
+(F-06): una sola versión `vigente` por (mes, rubro) — índice único parcial. Las
+aprobadas (monto_definido != null) generan versión nueva; el recálculo solo toca las
+nunca aprobadas. `ajustes` es append-only. `compromisos_programados` es una fila
+INFORMATIVA (Σ DeudaCuota), NO entra en la fórmula (regla 10)."""
+
+import re
+from datetime import datetime
+from decimal import Decimal
+from enum import StrEnum
+
+from beanie import Document, PydanticObjectId
+from pydantic import BaseModel, ConfigDict, Field, field_validator
+from pymongo import IndexModel
+
+from app.core.money import Money
+from app.core.time import now_utc
+
+PRESUPUESTO_COLLECTION = "presupuesto_lineas"
+_MES = re.compile(r"^\d{4}-\d{2}-01$")
+
+
+class ModoCalculo(StrEnum):
+    HISTORICO = "historico"
+    VENTAS = "ventas"  # Fase 1.5 (N-01); en go-live TODAS en histórico (N-03)
+
+
+class Ajuste(BaseModel):
+    """Un acotamiento del monto (append-only, F-06)."""
+
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    valor_anterior: Money | None = None
+    valor_nuevo: Money
+    por: str  # usuario_id
+    at: datetime
+
+
+class PresupuestoLinea(Document):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    mes_id: PydanticObjectId
+    rubro_id: PydanticObjectId
+    version: int = 1
+    monto_sugerido: Money
+    prom_3m: Money
+    tendencia_mes: Money  # puede ser negativa (rubro decreciente)
+    crec_pct: (
+        Money  # tasa; Money = Decimal que round-trip seguro (Decimal128 al releer)
+    )
+    compromisos_programados: Money = Decimal("0")  # informativo; NO entra en la fórmula
+    monto_definido: Money | None = None  # null hasta aprobar (F-07)
+    historia_incompleta: bool
+    modo_calculo: ModoCalculo = ModoCalculo.HISTORICO
+    ajustes: list[Ajuste] = Field(default_factory=list)
+    vigente: bool = True
+    creada_at: datetime = Field(default_factory=now_utc)
+
+    class Settings:
+        name = PRESUPUESTO_COLLECTION
+        indexes = [
+            IndexModel(
+                [("mes_id", 1), ("rubro_id", 1), ("version", 1)],
+                name="mes_rubro_version_unico",
+                unique=True,
+            ),
+            # F-06: una sola versión vigente por (mes, rubro).
+            IndexModel(
+                [("mes_id", 1), ("rubro_id", 1)],
+                name="vigente_unico",
+                unique=True,
+                partialFilterExpression={"vigente": True},
+            ),
+        ]
+
+    @field_validator("modo_calculo", mode="before")
+    @classmethod
+    def _cast_modo(cls, v: object) -> object:
+        return v if isinstance(v, ModoCalculo) else ModoCalculo(v)
+
+    @field_validator("creada_at")
+    @classmethod
+    def _aware(cls, v: datetime | None) -> datetime | None:
+        if v is not None and v.tzinfo is None:
+            raise ValueError("datetime debe ser UTC-aware (regla 2)")
+        return v
diff --git a/backend/app/presupuesto/__init__.py b/backend/app/presupuesto/__init__.py
new file mode 100644
index 0000000..e9173c8
--- /dev/null
+++ b/backend/app/presupuesto/__init__.py
@@ -0,0 +1,4 @@
+# backend/app/presupuesto/__init__.py
+"""Presupuesto: motor del sugerido (§1.4.1, F-07) y ciclo de aprobación (§2.4).
+El motor es una función PURA de Decimal; la generación de líneas y el versionado
+viven en el servicio."""
diff --git a/backend/app/presupuesto/motor.py b/backend/app/presupuesto/motor.py
new file mode 100644
index 0000000..80b69e0
--- /dev/null
+++ b/backend/app/presupuesto/motor.py
@@ -0,0 +1,62 @@
+# backend/app/presupuesto/motor.py
+"""Fórmula oficial del sugerido — Spec §1.4.1 (F-07). Función PURA (sin I/O),
+auditada por Kimi celda a celda contra el Excel congelado.
+
+    prom_3m       = (E(M-1) + E(M-2) + E(M-3)) / 3
+    tendencia_mes = (E(M-1) − E(M-3)) / 2
+    sugerido      = prom_3m + tendencia_mes + prom_3m × crec_pct
+
+E(i) = ejecutado del rubro en el mes i, usando EXCLUSIVAMENTE meses 'cerrado'.
+`historia_incompleta` = true si hay menos de 3 meses cerrados (el sugerido se
+calcula con los que haya). Todo en Decimal (regla 1); cuantización COP 2 decimales
+HALF_EVEN (misma política que `money_str`).
+
+**Decisión declarada (Kimi):** el Spec define la fórmula para n=3. Para n<3 se
+generaliza sin adivinar: `prom_3m` = promedio de los meses disponibles;
+`tendencia_mes` = (más_reciente − más_antiguo)/(n−1) —para n=3 da /2, exactamente la
+fórmula oficial— y 0 si n<2 (un punto no define pendiente); n=0 → todo 0. En todos
+esos casos `historia_incompleta=true`. En el go-live todas las líneas se generan con
+n=3 (may–jul cerrados y migrados), que es el caso certificado."""
+
+from dataclasses import dataclass
+from decimal import ROUND_HALF_EVEN, Decimal
+
+_CENTAVO = Decimal("0.01")
+
+
+def _cop(v: Decimal) -> Decimal:
+    return v.quantize(_CENTAVO, rounding=ROUND_HALF_EVEN)
+
+
+@dataclass(frozen=True)
+class ComponentesSugerido:
+    prom_3m: Decimal
+    tendencia_mes: Decimal
+    monto_sugerido: Decimal
+    historia_incompleta: bool
+
+
+def calcular_sugerido_historico(
+    ejecutados: list[Decimal], crec_pct: Decimal
+) -> ComponentesSugerido:
+    """`ejecutados` = ejecutado de meses CERRADOS, ordenados de MÁS RECIENTE a más
+    antiguo: [E(M-1), E(M-2), E(M-3), …]. Solo se usan los 3 más recientes."""
+    usados = ejecutados[:3]  # E(M-1..M-3); ignora historia más vieja
+    n = len(usados)
+    historia_incompleta = n < 3
+
+    if n == 0:
+        cero = _cop(Decimal("0"))
+        return ComponentesSugerido(cero, cero, cero, True)
+
+    prom_3m = sum(usados, Decimal("0")) / Decimal(n)
+    # tendencia: pendiente media entre el más reciente y el más antiguo disponible.
+    # n=3 → (E(M-1) − E(M-3))/2 (fórmula oficial); n=2 → /1; n=1 → 0.
+    tendencia = (usados[0] - usados[-1]) / Decimal(n - 1) if n >= 2 else Decimal("0")
+    sugerido = prom_3m + tendencia + prom_3m * crec_pct
+    return ComponentesSugerido(
+        prom_3m=_cop(prom_3m),
+        tendencia_mes=_cop(tendencia),
+        monto_sugerido=_cop(sugerido),
+        historia_incompleta=historia_incompleta,
+    )
diff --git a/backend/app/presupuesto/router.py b/backend/app/presupuesto/router.py
new file mode 100644
index 0000000..0ca3e0f
--- /dev/null
+++ b/backend/app/presupuesto/router.py
@@ -0,0 +1,94 @@
+# backend/app/presupuesto/router.py
+"""POST /api/v1/meses/{mes}/sugerido (generar) + GET /api/v1/meses/{mes}/presupuesto.
+
+MARCADO PARA AUDITORÍA KIMI (motor del sugerido).
+
+RBAC §2.4: generar = `ciclo:abrir` (fila "Abrir mes / generar sugerido"); leer =
+`dashboard:leer`. `crec_pct` viaja como string (Decimal exacto). `mes` en la ruta es
+YYYY-MM (se normaliza al día 1)."""
+
+import re
+from decimal import Decimal, InvalidOperation
+
+from fastapi import APIRouter, Depends, HTTPException
+from pydantic import BaseModel, ConfigDict
+
+from app.auth.deps import require_permission
+from app.auth.models import User
+from app.auth.router import verify_origin
+from app.core.money import money_str
+from app.domain.mes_control import MesControl
+from app.domain.presupuesto import PresupuestoLinea
+from app.presupuesto import service
+
+router = APIRouter(prefix="/meses", tags=["presupuesto"])
+
+_MES = re.compile(r"^\d{4}-\d{2}$")
+
+
+class GenerarSugeridoBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    crec_pct: str = "0"  # tasa como string (p. ej. "0.15"); Decimal exacto
+
+
+def _mes_key(mes: str) -> str:
+    if not _MES.match(mes):
+        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
+    return f"{mes}-01"
+
+
+def _serializar(ln: PresupuestoLinea) -> dict:
+    return {
+        "id": str(ln.id),
+        "rubro_id": str(ln.rubro_id),
+        "version": ln.version,
+        "monto_sugerido": money_str(ln.monto_sugerido),
+        "prom_3m": money_str(ln.prom_3m),
+        "tendencia_mes": money_str(ln.tendencia_mes),
+        "crec_pct": str(ln.crec_pct),
+        "compromisos_programados": money_str(ln.compromisos_programados),
+        "monto_definido": (
+            money_str(ln.monto_definido) if ln.monto_definido is not None else None
+        ),
+        "historia_incompleta": ln.historia_incompleta,
+        "modo_calculo": ln.modo_calculo.value,
+        "vigente": ln.vigente,
+    }
+
+
+@router.post("/{mes}/sugerido", status_code=201)
+async def generar_sugerido(
+    mes: str,
+    body: GenerarSugeridoBody,
+    user: User = Depends(require_permission("ciclo:abrir")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        crec = Decimal(body.crec_pct)
+    except InvalidOperation:
+        raise HTTPException(422, "crec_pct no es un decimal válido") from None
+    if crec < 0:
+        raise HTTPException(422, "crec_pct no puede ser negativo")
+    try:
+        lineas = await service.generar_sugerido(
+            mes=_mes_key(mes), usuario_id=user.id, crec_pct=crec
+        )
+    except service.SugeridoError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return {"mes": mes, "lineas": [_serializar(x) for x in lineas]}
+
+
+@router.get("/{mes}/presupuesto")
+async def listar_presupuesto(
+    mes: str,
+    user: User = Depends(require_permission("dashboard:leer")),
+):
+    mc = await MesControl.find_one(MesControl.mes == _mes_key(mes))
+    if mc is None:
+        raise HTTPException(404, "mes no encontrado")
+    lineas = await PresupuestoLinea.find(
+        PresupuestoLinea.mes_id == mc.id,
+        PresupuestoLinea.vigente == True,  # noqa: E712
+    ).to_list()
+    return {"mes": mes, "lineas": [_serializar(x) for x in lineas]}
diff --git a/backend/app/presupuesto/service.py b/backend/app/presupuesto/service.py
new file mode 100644
index 0000000..0294eff
--- /dev/null
+++ b/backend/app/presupuesto/service.py
@@ -0,0 +1,95 @@
+# backend/app/presupuesto/service.py
+"""Generación del sugerido (F-07): crea las PresupuestoLinea vigentes de un mes a
+partir del ejecutado de los meses CERRADOS anteriores (§1.4.1).
+
+MARCADO PARA AUDITORÍA KIMI (motor del sugerido — fórmula celda a celda).
+
+Alcance de este incremento: generar líneas en modo HISTÓRICO para los rubros
+activos NO de sistema ('Por clasificar'/'Ajuste'/'Recaudo' se excluyen — no son
+líneas presupuestables). El acotamiento (monto_definido) y la aprobación (→definido)
+son incrementos siguientes; aquí toda línea nace `vigente`, version 1, sin definir.
+
+E(i) = Σ valor de Transaccion (egreso) del rubro en el mes cerrado i. Se toman los 3
+meses 'cerrado' inmediatamente anteriores al mes objetivo (los que existan)."""
+
+from decimal import Decimal
+
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.presupuesto import PresupuestoLinea
+from app.domain.rubro import Rubro, TipoFlujo
+from app.domain.transaccion import Transaccion
+from app.presupuesto.motor import calcular_sugerido_historico
+
+
+class SugeridoError(Exception):
+    def __init__(self, detalle: str, status: int = 422) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+        self.status = status
+
+
+async def _meses_cerrados_previos(mes: str, limite: int = 3) -> list[MesControl]:
+    """Los `limite` meses en estado 'cerrado' con mes < objetivo, del más reciente
+    al más antiguo (E(M-1), E(M-2), E(M-3))."""
+    return (
+        await MesControl.find(
+            MesControl.estado == EstadoMes.CERRADO, MesControl.mes < mes
+        )
+        .sort(-MesControl.mes)
+        .limit(limite)
+        .to_list()
+    )
+
+
+async def _ejecutado(rubro_id, mes_id) -> Decimal:
+    """Σ valor de las transacciones de EGRESO del rubro en ese mes cerrado."""
+    total = Decimal("0")
+    async for t in Transaccion.find(
+        Transaccion.rubro_id == rubro_id,
+        Transaccion.mes_id == mes_id,
+        Transaccion.tipo_flujo == TipoFlujo.EGRESO,
+    ):
+        total += t.valor
+    return total
+
+
+async def generar_sugerido(
+    *, mes: str, usuario_id: str, crec_pct: Decimal = Decimal("0")
+) -> list[PresupuestoLinea]:
+    objetivo = await MesControl.find_one(MesControl.mes == mes)
+    if objetivo is None:
+        raise SugeridoError(f"el mes {mes[:7]} no está abierto")
+    if await PresupuestoLinea.find_one(PresupuestoLinea.mes_id == objetivo.id):
+        raise SugeridoError(
+            f"el mes {mes[:7]} ya tiene presupuesto generado", status=409
+        )
+
+    cerrados = await _meses_cerrados_previos(mes)
+    rubros = await Rubro.find(
+        Rubro.activo == True,  # noqa: E712 (Beanie construye el filtro)
+        Rubro.es_sistema == False,  # noqa: E712
+    ).to_list()
+
+    creadas: list[PresupuestoLinea] = []
+    for rubro in rubros:
+        ejecutados = [await _ejecutado(rubro.id, mc.id) for mc in cerrados]
+        comp = calcular_sugerido_historico(ejecutados, crec_pct)
+        linea = PresupuestoLinea(
+            mes_id=objetivo.id,
+            rubro_id=rubro.id,
+            monto_sugerido=comp.monto_sugerido,
+            prom_3m=comp.prom_3m,
+            tendencia_mes=comp.tendencia_mes,
+            crec_pct=crec_pct,
+            historia_incompleta=comp.historia_incompleta,
+        )
+        await linea.insert()
+        creadas.append(linea)
+
+    # DECISIÓN (Kimi): la generación NO emite evento. El catálogo cerrado (regla 11)
+    # no tiene 'sugerido.generado'; usar presupuesto.acotado sería mal uso semántico
+    # (acotar = ajustar una línea existente, no generarla). El sugerido es un
+    # BORRADOR recomputable (monto_definido=null); los eventos reales llegan con el
+    # acotamiento (presupuesto.acotado) y la aprobación (presupuesto.definido). Si el
+    # gate exige rastro de generación → CR para 'presupuesto.sugerido_generado'.
+    return creadas
diff --git a/backend/tests/test_db.py b/backend/tests/test_db.py
index 51d7e6c..3ca293c 100644
--- a/backend/tests/test_db.py
+++ b/backend/tests/test_db.py
@@ -19,7 +19,7 @@ async def test_init_beanie_registra_los_documents_de_dominio():
     from app.domain import DOMAIN_DOCUMENTS, Transaccion
 
     assert mongo.DOCUMENT_MODELS == DOMAIN_DOCUMENTS
-    assert len(DOMAIN_DOCUMENTS) == 6
+    assert len(DOMAIN_DOCUMENTS) == 7
     assert Transaccion in mongo.DOCUMENT_MODELS
     assert AuditLog not in mongo.DOCUMENT_MODELS
     client = AsyncMongoMockClient()
diff --git a/backend/tests/test_motor_sugerido.py b/backend/tests/test_motor_sugerido.py
new file mode 100644
index 0000000..09b4b45
--- /dev/null
+++ b/backend/tests/test_motor_sugerido.py
@@ -0,0 +1,97 @@
+# backend/tests/test_motor_sugerido.py
+"""Motor del sugerido — fórmula oficial §1.4.1 (F-07). NÚCLEO auditado por Kimi
+celda a celda.
+
+    prom_3m       = (E(M-1) + E(M-2) + E(M-3)) / 3
+    tendencia_mes = (E(M-1) − E(M-3)) / 2
+    sugerido      = prom_3m + tendencia_mes + prom_3m × crec_pct
+
+E(i) = ejecutado del rubro en el mes i, SOLO meses 'cerrado'. `historia_incompleta`
+= true si hay menos de 3 meses cerrados. Todo en Decimal (regla 1)."""
+
+from decimal import Decimal
+
+from app.presupuesto.motor import calcular_sugerido_historico
+
+
+def test_ejemplo_oficial_del_spec():
+    # Spec §1.4.1: E(abr)=48M, E(may)=61M, E(jun)=75M, crec 15% → jul = 84.033.333,33.
+    r = calcular_sugerido_historico(
+        ejecutados=[Decimal("75000000"), Decimal("61000000"), Decimal("48000000")],
+        crec_pct=Decimal("0.15"),
+    )
+    assert r.prom_3m == Decimal("61333333.33")
+    assert r.tendencia_mes == Decimal("13500000.00")
+    assert r.monto_sugerido == Decimal("84033333.33")
+    assert r.historia_incompleta is False
+
+
+def test_componentes_son_decimal():
+    r = calcular_sugerido_historico(
+        ejecutados=[Decimal("100"), Decimal("100"), Decimal("100")],
+        crec_pct=Decimal("0"),
+    )
+    for v in (r.prom_3m, r.tendencia_mes, r.monto_sugerido):
+        assert isinstance(v, Decimal) and not isinstance(v, float)
+
+
+def test_crec_cero_es_prom_mas_tendencia():
+    r = calcular_sugerido_historico(
+        ejecutados=[Decimal("120"), Decimal("100"), Decimal("80")],
+        crec_pct=Decimal("0"),
+    )
+    assert r.prom_3m == Decimal("100.00")
+    assert r.tendencia_mes == Decimal("20.00")  # (120−80)/2
+    assert r.monto_sugerido == Decimal("120.00")
+
+
+def test_tendencia_negativa_rubro_decreciente():
+    r = calcular_sugerido_historico(
+        ejecutados=[Decimal("80"), Decimal("100"), Decimal("120")],
+        crec_pct=Decimal("0"),
+    )
+    assert r.tendencia_mes == Decimal("-20.00")  # (80−120)/2
+    assert r.monto_sugerido == Decimal("80.00")  # 100 − 20
+
+
+def test_dos_meses_historia_incompleta():
+    # <3 cerrados → incompleta; tendencia = (reciente − antiguo)/(n−1) = /1.
+    r = calcular_sugerido_historico(
+        ejecutados=[Decimal("120"), Decimal("100")], crec_pct=Decimal("0")
+    )
+    assert r.historia_incompleta is True
+    assert r.prom_3m == Decimal("110.00")  # promedio de los 2 disponibles
+    assert r.tendencia_mes == Decimal("20.00")  # (120−100)/1
+
+
+def test_un_mes_sin_tendencia():
+    r = calcular_sugerido_historico(
+        ejecutados=[Decimal("100")], crec_pct=Decimal("0.10")
+    )
+    assert r.historia_incompleta is True
+    assert r.prom_3m == Decimal("100.00")
+    assert r.tendencia_mes == Decimal("0.00")  # 1 mes: no hay tendencia
+    assert r.monto_sugerido == Decimal("110.00")  # 100 + 0 + 100×0.10
+
+
+def test_sin_historia_todo_cero():
+    r = calcular_sugerido_historico(ejecutados=[], crec_pct=Decimal("0.15"))
+    assert r.historia_incompleta is True
+    assert r.prom_3m == Decimal("0.00")
+    assert r.tendencia_mes == Decimal("0.00")
+    assert r.monto_sugerido == Decimal("0.00")
+
+
+def test_mas_de_tres_meses_usa_solo_los_tres_recientes():
+    # Si llegan >3 (defensa), la fórmula usa E(M-1..M-3) — los 3 más recientes.
+    r = calcular_sugerido_historico(
+        ejecutados=[
+            Decimal("75000000"),
+            Decimal("61000000"),
+            Decimal("48000000"),
+            Decimal("999"),
+        ],
+        crec_pct=Decimal("0.15"),
+    )
+    assert r.monto_sugerido == Decimal("84033333.33")
+    assert r.historia_incompleta is False
diff --git a/backend/tests/test_presupuesto_generar.py b/backend/tests/test_presupuesto_generar.py
new file mode 100644
index 0000000..cb701bb
--- /dev/null
+++ b/backend/tests/test_presupuesto_generar.py
@@ -0,0 +1,189 @@
+# backend/tests/test_presupuesto_generar.py
+"""POST /meses/{mes}/sugerido — generación del sugerido end-to-end (F-07, §1.4.1).
+
+MARCADO PARA AUDITORÍA KIMI (motor del sugerido).
+
+El test estrella reproduce el ejemplo oficial del Spec §1.4.1 EN LA API: 3 meses
+cerrados con ejecutado 48M/61M/75M de un rubro + crec 15% → línea con sugerido
+84.033.333,33 y sus componentes. Cubre además: solo meses cerrados; RBAC; idempotencia
+(no regenerar); rubros de sistema excluidos; historia incompleta.
+"""
+
+from decimal import Decimal
+
+import httpx
+import pytest_asyncio
+from app.audit.service import configure_audit, reset_audit
+from app.auth import passwords, repository
+from app.auth.models import User
+from app.auth.roles import Role
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.rubro import Rubro
+from app.domain.transaccion import Transaccion
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
+    from app.main import create_app
+
+    app = create_app()
+    # tz_aware=True como el Motor real (mongo.create_client) → los datetime
+    # re-leídos vuelven UTC-aware (regla 2), no naive.
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
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def _token(ac, email="fin@roddos.com") -> dict:
+    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+async def _mes(mesd: str, estado: EstadoMes) -> MesControl:
+    mc = MesControl(mes=mesd, saldo_inicial_caja=Decimal("0"), estado=estado)
+    await mc.insert()
+    return mc
+
+
+async def _rubro(nombre: str, orden: int, sistema: bool = False) -> Rubro:
+    r = Rubro(grupo="operacion", nombre=nombre, orden=orden, es_sistema=sistema)
+    await r.insert()
+    return r
+
+
+_SEQ = [0]
+
+
+async def _ejec(rubro_id, mes_id, monto: str):
+    """Una transacción de egreso que aporta `monto` al ejecutado del rubro/mes."""
+    _SEQ[0] += 1
+    await Transaccion(
+        fecha="2026-01-15",
+        descripcion="EJEC",
+        valor=Decimal(monto),
+        tipo_flujo="egreso",
+        rubro_id=rubro_id,
+        mes_id=mes_id,
+        banco="manual",
+        id_banco=f"MAN-EJEC-{_SEQ[0]}",
+    ).insert()
+
+
+async def test_ejemplo_oficial_end_to_end(api):
+    # Spec §1.4.1 vía API: abr/may/jun cerrados 48/61/75M → jul sugerido 84.033.333,33
+    h = await _token(api)
+    abr = await _mes("2026-04-01", EstadoMes.CERRADO)
+    may = await _mes("2026-05-01", EstadoMes.CERRADO)
+    jun = await _mes("2026-06-01", EstadoMes.CERRADO)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)  # objetivo (abierto)
+    rubro = await _rubro("Arriendos", 4)
+    # dos transacciones en un mes para verificar que E(i) SUMA
+    await _ejec(rubro.id, abr.id, "20000000")
+    await _ejec(rubro.id, abr.id, "28000000")  # abr total 48M
+    await _ejec(rubro.id, may.id, "61000000")
+    await _ejec(rubro.id, jun.id, "75000000")
+
+    r = await api.post(
+        "/api/v1/meses/2026-07/sugerido", json={"crec_pct": "0.15"}, headers=h
+    )
+    assert r.status_code == 201
+    ln = next(x for x in r.json()["lineas"] if x["rubro_id"] == str(rubro.id))
+    assert ln["prom_3m"] == "61333333.33"
+    assert ln["tendencia_mes"] == "13500000.00"
+    assert ln["monto_sugerido"] == "84033333.33"
+    assert ln["historia_incompleta"] is False
+    assert ln["monto_definido"] is None
+    assert ln["vigente"] is True
+
+
+async def test_solo_cuenta_meses_cerrados(api):
+    # Un mes EN_EJECUCION no cuenta como historia (solo 'cerrado').
+    h = await _token(api)
+    jun = await _mes("2026-06-01", EstadoMes.CERRADO)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)  # abierto, no cerrado
+    await _mes("2026-08-01", EstadoMes.SUGERIDO)  # objetivo
+    rubro = await _rubro("Arriendos", 4)
+    await _ejec(rubro.id, jun.id, "50000000")
+    r = await api.post("/api/v1/meses/2026-08/sugerido", json={}, headers=h)
+    ln = next(x for x in r.json()["lineas"] if x["rubro_id"] == str(rubro.id))
+    assert ln["historia_incompleta"] is True  # solo 1 mes cerrado
+    assert ln["prom_3m"] == "50000000.00"
+
+
+async def test_excluye_rubros_de_sistema(api):
+    h = await _token(api)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    await _rubro("Arriendos", 4)
+    await _rubro("Por clasificar", 98, sistema=True)
+    await _rubro("Recaudo", 99, sistema=True)
+    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
+    nombres_generados = len(r.json()["lineas"])
+    assert nombres_generados == 1  # solo Arriendos, no los de sistema
+
+
+async def test_no_regenera_409(api):
+    h = await _token(api)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    await _rubro("Arriendos", 4)
+    await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
+    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
+    assert r.status_code == 409
+
+
+async def test_mes_inexistente_422(api):
+    h = await _token(api)
+    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
+    assert r.status_code == 422
+
+
+async def test_consulta_403(api):
+    h = await _token(api, "consulta@roddos.com")
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
+    assert r.status_code == 403
+
+
+async def test_crec_negativo_422(api):
+    h = await _token(api)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    r = await api.post(
+        "/api/v1/meses/2026-07/sugerido", json={"crec_pct": "-0.1"}, headers=h
+    )
+    assert r.status_code == 422
+
+
+async def test_listar_presupuesto(api):
+    h = await _token(api)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    await _rubro("Arriendos", 4)
+    await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
+    r = await api.get("/api/v1/meses/2026-07/presupuesto", headers=h)
+    assert r.status_code == 200
+    assert len(r.json()["lineas"]) == 1
+    assert r.json()["lineas"][0]["vigente"] is True
```
