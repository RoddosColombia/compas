# EVIDENCIA — sprint1-parsers · PR1-I

Merge `0a3f1fa` (commits `7285c34` código + `b23a2ee` tracker). Código real + salidas reales (no descripciones).

## 1. pytest (suite local, mongomock)

```
209 passed, 19 skipped, 9 warnings in 72.33s (0:01:12)
```

## 2. pytest @requires_real_mongo (Mongo real — carga + dedup)

Contra el cluster Atlas compartido, en bases `compas_test_*` (aisladas de SISMO; drop_database antes/después).

```
8 passed, 4 deselected, 79 warnings in 76.26s (0:01:16)
```

Cobertura real-mongo: dedup índice único parcial (solape no duplica, 2 manuales coexisten) + carga (completada, solape, F-02 rechazo, mes ausente→errores, evento carga.completada).

## 3. ruff

```
All checks passed!
```

## 4. Protocolo de commit

```
r1:0 | journal-entries:0 | estado-pending:0
```

## 5. git diff --stat (a7aee40..7285c34)

```
backend/app/cargas/__init__.py          |   3 +
 backend/app/cargas/mapper.py            |  56 ++++++
 backend/app/cargas/service.py           | 179 +++++++++++++++++
 backend/app/domain/__init__.py          |  19 +-
 backend/app/domain/bancos.py            |   4 +-
 backend/app/domain/carga.py             |  93 +++++++++
 backend/app/domain/transaccion.py       | 135 +++++++++++++
 backend/app/parsers/__init__.py         |   5 +
 backend/app/parsers/bank_parsers.py     | 346 ++++++++++++++++++++++++++++++++
 backend/tests/test_bank_parsers.py      | 274 +++++++++++++++++++++++++
 backend/tests/test_carga.py             | 168 ++++++++++++++++
 backend/tests/test_db.py                |  10 +-
 backend/tests/test_real_mongo_marker.py |   8 +-
 backend/tests/test_transaccion.py       | 188 +++++++++++++++++
 backend/tests/test_transaccion_dedup.py |  69 +++++++
 15 files changed, 1546 insertions(+), 11 deletions(-)
```

## 6. Código fuente (archivos nuevos — objetivo de la auditoría)

### `backend/app/parsers/bank_parsers.py`

```python
# backend/app/parsers/bank_parsers.py
"""Parsers de extractos bancarios — Bancolombia, BBVA, Global66 (Spec §1.5).

Portados en espíritu de SISMO v2 (`services/bank_parsers.py`) y adaptados a las
reglas innegociables de COMPAS:

  - **Regla 1 (Decimal, nunca float):** los montos se construyen como `Decimal`
    vía el tipo `Money`, que rechaza `float`. Los números de openpyxl (que llegan
    como `float`) se convierten con `Decimal(str(v))` para no arrastrar ruido binario.
  - **Regla 7 (transforma, no interpreta):** una fila con fecha o monto no
    parseables NO se adivina ni se traga en silencio: se acumula en
    `ResultadoParseo.errores` con el número de fila. Solo las filas totalmente
    vacías (o de valor 0, que no son movimiento de caja) se omiten sin error.
  - **Regla 7 (Global66):** se conservan `moneda_original` y `tasa_cambio`. Hoy
    solo se lee la hoja 'Movimientos de cuenta COP' → `moneda_original='COP'`,
    `tasa_cambio=1` (es un hecho de esa hoja, no una interpretación). El mapeo FX
    multi-moneda real requiere un export Global66 de muestra (TODO Sprint 1).

Formatos (heredados de la realidad de cada banco):
  - Bancolombia: .xlsx, hoja 'Extracto', headers fila 15, fecha d/m sin año.
  - BBVA: .xlsx, hoja activa, headers fila 14, fecha d-m-Y.
  - Global66: .xls/.xlsx, hoja 'Movimientos de cuenta COP', headers fila 4.
"""

import os
import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

import openpyxl
from pydantic import BaseModel, ConfigDict

from app.core.money import Money
from app.core.time import now_bogota
from app.domain.bancos import Banco


class TipoMovimiento(StrEnum):
    DEBITO = "debito"
    CREDITO = "credito"


class MovimientoBancario(BaseModel):
    """Un movimiento parseado, normalizado y con dinero en Decimal (regla 1)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    fecha: date
    descripcion: str
    monto: Money  # positivo (magnitud); el signo vive en `tipo`
    tipo: TipoMovimiento
    banco: Banco
    # Global66 (regla 7): moneda de origen y tasa aplicada.
    moneda_original: str | None = None
    tasa_cambio: Decimal | None = None
    referencia: str | None = None


class ErrorFila(BaseModel):
    """Fila que el parser no pudo transformar sin adivinar (regla 7)."""

    fila: int
    motivo: str
    valor_crudo: str | None = None


class ResultadoParseo(BaseModel):
    banco: Banco
    movimientos: list[MovimientoBancario]
    errores: list[ErrorFila]


class _FilaError(Exception):
    """Interno: se eleva por fila y se convierte en `ErrorFila`."""

    def __init__(self, motivo: str, valor_crudo: str | None = None) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.valor_crudo = valor_crudo


# ── Utilidades ───────────────────────────────────────────────────────────


def _open_workbook(file_path: str):
    """Abre el .xlsx; si la extensión .xls confunde a openpyxl, copia a temp."""
    try:
        return openpyxl.load_workbook(file_path, data_only=True)
    except Exception:
        tmp = os.path.join(tempfile.mkdtemp(), "extract.xlsx")
        shutil.copy2(file_path, tmp)
        return openpyxl.load_workbook(tmp, data_only=True)


def _cell(row: tuple, idx: int):
    return row[idx] if idx is not None and idx < len(row) else None


def _fila_vacia(row: tuple) -> bool:
    return all(
        v is None or (isinstance(v, str) and v.strip() == "") for v in row
    )


def _mapear_columnas(ws, header_row: int, spec: dict[str, str]) -> dict[str, int]:
    """Ubica columnas por substring del header (case-insensitive)."""
    headers = [str(c.value or "").strip().upper() for c in ws[header_row]]
    col: dict[str, int] = {}
    for key, needle in spec.items():
        for i, h in enumerate(headers):
            if needle in h:
                col[key] = i
                break
    faltan = [k for k in spec if k not in col]
    if faltan:
        raise ValueError(
            f"Columnas no encontradas en la fila {header_row}: {faltan}. "
            f"Headers vistos: {headers}"
        )
    return col


def _a_decimal(valor) -> Decimal:
    """Convierte un valor de celda a Decimal con signo. Eleva `_FilaError` si es
    ambiguo (regla 7: no se adivina 0)."""
    if valor is None:
        raise _FilaError("monto vacío")
    if isinstance(valor, bool):  # bool es subclase de int
        raise _FilaError("monto booleano inválido", str(valor))
    if isinstance(valor, (int, float, Decimal)):
        return Decimal(str(valor))
    s = str(valor).strip().replace("$", "").replace(" ", "")
    if s == "":
        raise _FilaError("monto vacío", str(valor))
    negativo = s.startswith("-")
    s = s.lstrip("+-").replace(",", "")  # coma = separador de miles
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise _FilaError("monto no numérico", str(valor)) from None
    return -d if negativo else d


def _fecha_dmy(raw, con_anio: bool) -> date:
    """Parsea fecha. `con_anio=False` → formato d/m sin año (Bancolombia): se
    completa con el año actual (Bogotá)."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if con_anio:
        try:
            return datetime.strptime(s, "%d-%m-%Y").date()
        except (ValueError, TypeError):
            raise _FilaError("fecha inválida", s) from None
    # Bancolombia: d/m (sin año) → completar con el año actual (Bogotá); o d/m/Y
    # explícito. Se antepone el año en vez de usar el default yearless de strptime
    # (DeprecationWarning en py3.15, y falla el 29-feb).
    anio = now_bogota().year
    for candidato in (f"{s}/{anio}", s):
        try:
            return datetime.strptime(candidato, "%d/%m/%Y").date()
        except (ValueError, TypeError):
            continue
    raise _FilaError("fecha inválida", s) from None


def _fecha_iso(raw) -> date:
    """Global66: 'YYYY-MM-DD HH:MM:SS' (o datetime)."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    raise _FilaError("fecha inválida", s)


# ── Detección ──────────────────────────────────────────────────────────────


def detectar_banco(file_path: str) -> Banco:
    """Auto-detecta el banco. Lanza ValueError en formato/estructura no soportada."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in (".xlsx", ".xls"):
        raise ValueError(
            f"Formato no soportado: {ext or '(sin extensión)'}. COMPAS procesa "
            ".xlsx/.xls (Bancolombia, BBVA, Global66)."
        )
    wb = _open_workbook(file_path)
    try:
        nombres = wb.sheetnames
        if any("Movimientos de cuenta COP" in n for n in nombres):
            return Banco.GLOBAL66
        if "Extracto" in nombres:
            return Banco.BANCOLOMBIA
        ws = wb.active
        fila14 = [str(c.value or "") for c in ws[14]]
        if any("FECHA DE OPERACI" in c.upper() for c in fila14):
            return Banco.BBVA
        raise ValueError(
            "No se pudo identificar el banco (Bancolombia/BBVA/Global66)."
        )
    finally:
        wb.close()


# ── Parsers por banco ────────────────────────────────────────────────────


def _parse_signo(
    file_path: str, banco: Banco, hoja: str | None, header_row: int, con_anio: bool
) -> ResultadoParseo:
    """Común a Bancolombia/BBVA: FECHA/DESCRIPCIÓN/VALOR con signo en el monto."""
    wb = _open_workbook(file_path)
    movimientos: list[MovimientoBancario] = []
    errores: list[ErrorFila] = []
    try:
        ws = wb[hoja] if hoja else wb.active
        col = _mapear_columnas(
            ws,
            header_row,
            {"fecha": "FECHA", "descripcion": "CONCEPTO" if banco is Banco.BBVA
             else "DESCRIPCI", "valor": "IMPORTE" if banco is Banco.BBVA
             else "VALOR"},
        )
        for r_idx, row in enumerate(
            ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1
        ):
            if _fila_vacia(row):
                continue
            try:
                fecha = _fecha_dmy(_cell(row, col["fecha"]), con_anio)
                signed = _a_decimal(_cell(row, col["valor"]))
                if signed == 0:
                    continue
                mov = MovimientoBancario(
                    fecha=fecha,
                    descripcion=str(_cell(row, col["descripcion"]) or "").strip(),
                    monto=abs(signed),
                    tipo=(
                        TipoMovimiento.DEBITO
                        if signed < 0
                        else TipoMovimiento.CREDITO
                    ),
                    banco=banco,
                )
            except _FilaError as e:
                errores.append(
                    ErrorFila(fila=r_idx, motivo=e.motivo, valor_crudo=e.valor_crudo)
                )
                continue
            movimientos.append(mov)
    finally:
        wb.close()
    return ResultadoParseo(banco=banco, movimientos=movimientos, errores=errores)


def parse_bancolombia(file_path: str) -> ResultadoParseo:
    return _parse_signo(file_path, Banco.BANCOLOMBIA, "Extracto", 15, con_anio=False)


def parse_bbva(file_path: str) -> ResultadoParseo:
    return _parse_signo(file_path, Banco.BBVA, None, 14, con_anio=True)


def parse_global66(file_path: str) -> ResultadoParseo:
    """Global66: hoja 'Movimientos de cuenta COP'. Débito en col C, crédito en D."""
    wb = _open_workbook(file_path)
    movimientos: list[MovimientoBancario] = []
    errores: list[ErrorFila] = []
    try:
        ws = None
        for nombre in wb.sheetnames:
            if "Movimientos de cuenta COP" in nombre:
                ws = wb[nombre]
                break
        if ws is None:
            raise ValueError("No se encontró la hoja 'Movimientos de cuenta COP'.")
        for r_idx, row in enumerate(ws.iter_rows(min_row=5, values_only=True), start=5):
            if _fila_vacia(row):
                continue
            debito, credito = _cell(row, 2), _cell(row, 3)
            tiene_deb = debito not in (None, "", 0)
            tiene_cred = credito not in (None, "", 0)
            if not tiene_deb and not tiene_cred:
                continue  # GMF informativo / fila sin valor
            try:
                fecha = _fecha_iso(_cell(row, 1))
                if tiene_deb:
                    monto, tipo = abs(_a_decimal(debito)), TipoMovimiento.DEBITO
                else:
                    monto, tipo = abs(_a_decimal(credito)), TipoMovimiento.CREDITO
                if monto == 0:
                    continue
                partes = [
                    p
                    for p in (
                        str(_cell(row, 0) or "").strip(),
                        str(_cell(row, 13) or "").strip(),
                        str(_cell(row, 7) or "").strip(),
                    )
                    if p
                ]
                ref = str(_cell(row, 12) or "").strip() or None
                mov = MovimientoBancario(
                    fecha=fecha,
                    descripcion=" — ".join(partes),
                    monto=monto,
                    tipo=tipo,
                    banco=Banco.GLOBAL66,
                    moneda_original="COP",
                    tasa_cambio=Decimal("1"),
                    referencia=ref,
                )
            except _FilaError as e:
                errores.append(
                    ErrorFila(fila=r_idx, motivo=e.motivo, valor_crudo=e.valor_crudo)
                )
                continue
            movimientos.append(mov)
    finally:
        wb.close()
    return ResultadoParseo(
        banco=Banco.GLOBAL66, movimientos=movimientos, errores=errores
    )


def parse_extracto(file_path: str, banco: Banco | None = None) -> ResultadoParseo:
    """Punto de entrada: auto-detecta el banco (si no se pasa) y rutea."""
    if banco is None:
        banco = detectar_banco(file_path)
    if banco is Banco.BANCOLOMBIA:
        return parse_bancolombia(file_path)
    if banco is Banco.BBVA:
        return parse_bbva(file_path)
    if banco is Banco.GLOBAL66:
        return parse_global66(file_path)
    raise ValueError(f"Banco no soportado: {banco}")
```

### `backend/app/domain/transaccion.py`

```python
# backend/app/domain/transaccion.py
"""Transaccion (Spec §1.5): un movimiento bancario ya normalizado y persistible.

Reglas:
  - Regla 1: `valor` es Money (Decimal), siempre > 0. El signo lo define `tipo_flujo`.
  - Regla 2: `fecha` como string 'YYYY-MM-DD' (mismo criterio que MesControl: BSON
    no tiene fecha-sin-hora). `mes_id` referencia el MesControl derivado de la fecha.
  - Regla 5: deduplicación en la BD por índice ÚNICO PARCIAL (banco, id_banco) con
    `partialFilterExpression {id_banco: {$type:'string'}}`. `id_banco` es determinista
    (ver `derivar_id_banco`) → re-cargar un extracto solapado no duplica.
  - Global66 (regla 7): conserva `moneda_original`/`valor_original`/`tasa_cambio`/
    `tasa_fuente` cuando el extracto no viene en COP (hoy la hoja COP → 'COP'/1).

`id_banco`: de extracto si banco≠manual (Global66: referencia nativa; Bancolombia/
BBVA: huella determinista, no traen ID); manuales 'MAN-'+ULID (F-04, feature aparte).
La inmutabilidad de fecha/valor/moneda/tasa/id_banco/banco (Spec §2.2) se hace cumplir
en la capa de servicio (no se actualizan esos campos), no en el modelo.
"""

import hashlib
import re
from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money
from app.domain.bancos import Banco
from app.domain.rubro import TipoFlujo

TRANSACCIONES_COLLECTION = "transacciones"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def derivar_id_banco(
    *,
    banco: Banco,
    fecha: str,
    descripcion: str,
    valor,
    tipo_flujo: TipoFlujo,
    referencia: str | None = None,
) -> str:
    """Clave de deduplicación estable (regla 5).

    - Global66 trae una referencia de transacción nativa → se usa tal cual.
    - Bancolombia/BBVA no traen ID → huella determinista del contenido
      (banco|fecha|tipo|descripcion|valor), precedente de SISMO v2. MD5 (no
      criptográfico, solo fingerprint) = 32 hex, cabe en String(40).
    """
    if banco is Banco.GLOBAL66 and referencia:
        return referencia
    clave = f"{banco.value}|{fecha}|{tipo_flujo.value}|{descripcion}|{valor:.2f}"
    return hashlib.md5(clave.encode("utf-8"), usedforsecurity=False).hexdigest()


class Transaccion(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    fecha: str  # 'YYYY-MM-DD'
    descripcion: str = Field(max_length=300)
    valor: Money  # > 0 (magnitud); el signo lo da tipo_flujo
    tipo_flujo: TipoFlujo
    rubro_id: PydanticObjectId  # default 'Por clasificar' (lo resuelve el servicio)
    mes_id: PydanticObjectId  # MesControl derivado de la fecha
    banco: Banco
    id_banco: str = Field(max_length=40)
    tardia: bool = False

    # Moneda extranjera (Global66, regla 7) — condicional.
    moneda_original: str | None = None
    valor_original: Money | None = None
    tasa_cambio: Money | None = None
    tasa_fuente: str | None = None

    # Origen y auditoría de clasificación (§1.5).
    carga_id: PydanticObjectId | None = None
    clasificada_por: str | None = None
    clasificada_at: datetime | None = None
    pago_planeado_id: PydanticObjectId | None = None
    factura_id: PydanticObjectId | None = None
    regla_id: PydanticObjectId | None = None

    class Settings:
        name = TRANSACCIONES_COLLECTION
        indexes = [
            # Regla 5: dedup. Único solo donde id_banco es string (siempre, hoy);
            # el partial deja la puerta para docs legacy sin id_banco string.
            IndexModel(
                [("banco", 1), ("id_banco", 1)],
                name="banco_idbanco_unico",
                unique=True,
                partialFilterExpression={"id_banco": {"$type": "string"}},
            ),
            IndexModel([("mes_id", 1)], name="por_mes"),
            IndexModel([("rubro_id", 1)], name="por_rubro"),
            IndexModel([("carga_id", 1)], name="por_carga"),
        ]

    @field_validator("fecha")
    @classmethod
    def _fecha_str(cls, v: object) -> str:
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("fecha debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha inválida: {v}") from e
        return v

    @field_validator("valor")
    @classmethod
    def _valor_positivo(cls, v):
        if v <= 0:
            raise ValueError("valor debe ser > 0; el signo lo define tipo_flujo")
        return v

    @field_validator("banco", mode="before")
    @classmethod
    def _cast_banco(cls, v: object) -> object:
        return v if isinstance(v, Banco) else Banco(v)

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)

    @field_validator("clasificada_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v
```

### `backend/app/domain/carga.py`

```python
# backend/app/domain/carga.py
"""CargaBancaria (Spec §1.6): ciclo de vida de una carga de extracto (F-02).

Inserción idempotente por lotes (§1.6): `insertMany ordered=False`, duplicados
contados por DuplicateKeyError contra el índice único parcial (banco, id_banco) de
Transaccion. El rechazo por `archivo_hash` aplica SOLO si existe una carga previa
'completada' con ese hash; si la previa está 'fallida', la re-carga se permite (la
dedup por (banco, id_banco) hace el reintento seguro).

`archivo_s3_key` es opcional: el almacenamiento del original en S3 está diferido
(RUNBOOK §6, S3 pendiente). Desviación documentada del §1.6 (Req) → gate Kimi.
"""

import re
from datetime import datetime
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.time import now_utc
from app.domain.bancos import Banco

CARGAS_COLLECTION = "cargas"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EstadoCarga(StrEnum):
    PROCESANDO = "procesando"
    COMPLETADA = "completada"
    FALLIDA = "fallida"


class ErrorCarga(BaseModel):
    """Fila del extracto que no se pudo transformar/ubicar (regla 7)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    fila: int  # número de fila del extracto; -1 = error no ligado a una fila
    motivo: str


class CargaBancaria(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    banco: Banco  # solo bancos reales (no 'manual')
    archivo_nombre: str
    archivo_hash: str  # SHA-256 hex del archivo (dedup de archivo, F-02)
    archivo_s3_key: str | None = None  # S3 diferido (RUNBOOK §6)
    total_filas: int = 0
    nuevas: int = 0
    duplicadas: int = 0
    errores: int = 0
    errores_detalle: list[ErrorCarga] = Field(default_factory=list)
    estado: EstadoCarga = EstadoCarga.PROCESANDO
    motivo_fallo: str | None = None
    usuario_id: PydanticObjectId
    created_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = CARGAS_COLLECTION
        indexes = [
            IndexModel([("archivo_hash", 1), ("estado", 1)], name="hash_estado"),
        ]

    @field_validator("banco", mode="before")
    @classmethod
    def _cast_banco(cls, v: object) -> object:
        b = v if isinstance(v, Banco) else Banco(v)
        if b is Banco.MANUAL:
            raise ValueError("una carga proviene de un banco real, no 'manual'")
        return b

    @field_validator("archivo_hash")
    @classmethod
    def _hash_sha256(cls, v: object) -> str:
        if not isinstance(v, str) or not _SHA256.match(v):
            raise ValueError("archivo_hash debe ser SHA-256 hex (64 chars)")
        return v

    @field_validator("estado", mode="before")
    @classmethod
    def _cast_estado(cls, v: object) -> object:
        return v if isinstance(v, EstadoCarga) else EstadoCarga(v)

    @field_validator("created_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v
```

### `backend/app/cargas/mapper.py`

```python
# backend/app/cargas/mapper.py
"""Puente parser → dominio: MovimientoBancario (DTO del parser) → Transaccion.

Puro y sin Mongo: el servicio de carga resuelve `rubro_id` ('Por clasificar') y
`mes_id` (MesControl del mes derivado de la fecha) y se los pasa aquí. La
derivación de `id_banco` y el mapeo tipo(débito/crédito)→tipo_flujo(egreso/ingreso)
viven aquí para que sean verificables sin base de datos.
"""

from beanie import PydanticObjectId

from app.domain.rubro import TipoFlujo
from app.domain.transaccion import Transaccion, derivar_id_banco
from app.parsers.bank_parsers import MovimientoBancario, TipoMovimiento

_TIPO_A_FLUJO = {
    TipoMovimiento.CREDITO: TipoFlujo.INGRESO,  # entra plata
    TipoMovimiento.DEBITO: TipoFlujo.EGRESO,  # sale plata
}


def movimiento_a_transaccion(
    mov: MovimientoBancario,
    *,
    rubro_id: PydanticObjectId,
    mes_id: PydanticObjectId,
    carga_id: PydanticObjectId | None = None,
) -> Transaccion:
    """Construye una Transaccion 'Por clasificar' a partir de un movimiento parseado."""
    fecha = mov.fecha.isoformat()  # date → 'YYYY-MM-DD'
    tipo_flujo = _TIPO_A_FLUJO[mov.tipo]
    id_banco = derivar_id_banco(
        banco=mov.banco,
        fecha=fecha,
        descripcion=mov.descripcion,
        valor=mov.monto,
        tipo_flujo=tipo_flujo,
        referencia=mov.referencia,
    )
    # Moneda extranjera (Global66): si el parser capturó moneda, se conserva el
    # original re-derivable (hoy la hoja COP → 'COP'/1; valor_original == valor).
    valor_original = mov.monto if mov.moneda_original is not None else None
    return Transaccion(
        fecha=fecha,
        descripcion=mov.descripcion,
        valor=mov.monto,
        tipo_flujo=tipo_flujo,
        rubro_id=rubro_id,
        mes_id=mes_id,
        banco=mov.banco,
        id_banco=id_banco,
        moneda_original=mov.moneda_original,
        valor_original=valor_original,
        tasa_cambio=mov.tasa_cambio,
        carga_id=carga_id,
    )
```

### `backend/app/cargas/service.py`

```python
# backend/app/cargas/service.py
"""Servicio de carga bancaria (Spec §1.6, PRD M7).

MARCADO PARA AUDITORÍA KIMI (flujo crítico: cargas bancarias).

Contrato seguido (§1.6, el data dictionary manda): inserción idempotente por lotes
`insertMany ordered=False`; los duplicados se cuentan por DuplicateKeyError contra el
índice único parcial (banco, id_banco). Esto NO es una transacción multi-documento
(la regla 8 la pide para 'finalización de carga', pero es incompatible con el
conteo-y-continúa del §1.6 → nota/CR pendiente, se resuelve en el gate Kimi).

F-02 (reproceso): se rechaza solo si ya hay una carga 'completada' con el mismo
archivo_hash; si la previa quedó 'fallida', la re-carga se permite y la dedup por
(banco, id_banco) evita duplicar lo ya insertado.
"""

import hashlib

from anyio import to_thread
from beanie import PydanticObjectId
from pymongo.errors import BulkWriteError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cargas.mapper import movimiento_a_transaccion
from app.domain.bancos import Banco
from app.domain.carga import CargaBancaria, ErrorCarga, EstadoCarga
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion

RUBRO_POR_CLASIFICAR = "Por clasificar"


class CargaError(Exception):
    """Error de negocio del flujo de carga."""


class CargaDuplicadaError(CargaError):
    """El archivo ya fue cargado con éxito (misma huella, estado completada)."""


class RubroPorClasificarAusenteError(CargaError):
    """Falta el rubro de sistema 'Por clasificar' (no se corrieron las semillas)."""


def _mes_de(fecha_iso: str) -> str:
    """Mes-llave (YYYY-MM-01) derivado de la fecha 'YYYY-MM-DD'."""
    return fecha_iso[:7] + "-01"


def _hash_archivo(archivo_path: str) -> str:
    """SHA-256 del archivo. Bloqueante → se corre en threadpool (§1.6)."""
    with open(archivo_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


async def procesar_carga(
    *,
    banco: Banco,
    archivo_path: str,
    archivo_nombre: str,
    usuario_id: PydanticObjectId,
    archivo_s3_key: str | None = None,
) -> CargaBancaria:
    """Parsea un extracto y persiste sus movimientos como Transaccion 'Por
    clasificar', idempotentemente. Devuelve la CargaBancaria con los conteos."""
    if banco is Banco.MANUAL:
        raise CargaError("una carga proviene de un banco real, no 'manual'")

    archivo_hash = await to_thread.run_sync(_hash_archivo, archivo_path)

    # F-02: solo bloquea una carga PREVIA COMPLETADA con el mismo hash.
    previa = await CargaBancaria.find_one(
        CargaBancaria.archivo_hash == archivo_hash,
        CargaBancaria.estado == EstadoCarga.COMPLETADA,
    )
    if previa is not None:
        raise CargaDuplicadaError(
            f"el archivo ya fue cargado (hash {archivo_hash[:8]}…, carga {previa.id})"
        )

    rubro = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
    if rubro is None:
        raise RubroPorClasificarAusenteError(
            "falta el rubro de sistema 'Por clasificar' (correr semillas de rubros)"
        )

    carga = CargaBancaria(
        banco=banco,
        archivo_nombre=archivo_nombre,
        archivo_hash=archivo_hash,
        archivo_s3_key=archivo_s3_key,
        usuario_id=usuario_id,
    )
    await carga.insert()

    try:
        # Parseo en threadpool para no bloquear el event loop (§1.6).
        resultado = await to_thread.run_sync(parse_extracto_seguro, archivo_path, banco)
        errores = [ErrorCarga(fila=e.fila, motivo=e.motivo) for e in resultado.errores]

        docs: list[Transaccion] = []
        for mov in resultado.movimientos:
            mes = _mes_de(mov.fecha.isoformat())
            mc = await MesControl.find_one(MesControl.mes == mes)
            if mc is None:
                errores.append(
                    ErrorCarga(
                        fila=-1,
                        motivo=f"mes {mes[:7]} sin MesControl abierto; omitido",
                    )
                )
                continue
            docs.append(
                movimiento_a_transaccion(
                    mov, rubro_id=rubro.id, mes_id=mc.id, carga_id=carga.id
                )
            )

        nuevas = duplicadas = 0
        if docs:
            try:
                res = await Transaccion.insert_many(docs, ordered=False)
                nuevas = len(res.inserted_ids)
            except BulkWriteError as bwe:
                write_errors = bwe.details.get("writeErrors", [])
                otros = [e for e in write_errors if e.get("code") != 11000]
                if otros:
                    raise  # error real (no un duplicado) → carga fallida
                duplicadas = len(write_errors)
                nuevas = bwe.details.get("nInserted", len(docs) - duplicadas)

        carga.total_filas = len(resultado.movimientos) + len(resultado.errores)
        carga.nuevas = nuevas
        carga.duplicadas = duplicadas
        carga.errores = len(errores)
        carga.errores_detalle = errores
        carga.estado = EstadoCarga.COMPLETADA
        await carga.save()

        await emit_audit(
            AuditEvento.carga_completada,
            entidad="carga",
            entidad_id=str(carga.id),
            actor_id=str(usuario_id),
            metadata={
                "banco": banco.value,
                "nuevas": nuevas,
                "duplicadas": duplicadas,
                "errores": len(errores),
            },
        )
        return carga

    except CargaError:
        raise
    except Exception as exc:
        carga.estado = EstadoCarga.FALLIDA
        carga.motivo_fallo = str(exc)[:500]
        await carga.save()
        try:
            await emit_audit(
                AuditEvento.carga_fallida,
                entidad="carga",
                entidad_id=str(carga.id),
                actor_id=str(usuario_id),
                metadata={"motivo": carga.motivo_fallo},
            )
        except Exception:  # noqa: BLE001 — no enmascarar el error original de la carga
            pass
        raise


def parse_extracto_seguro(archivo_path: str, banco: Banco):
    """Wrapper síncrono para el threadpool (import perezoso del parser)."""
    from app.parsers.bank_parsers import parse_extracto

    return parse_extracto(archivo_path, banco)
```

### `backend/app/domain/bancos.py`

```python
# backend/app/domain/bancos.py
"""Bancos de RODDOS (CLAUDE.md: Bancolombia, BBVA, Global66).

Enum compartido para no tener texto libre ('Bancolombia' vs 'bancolombia' vs
'BANCOLOMBIA' serían tres bancos distintos en la conciliación — Kimi B-2). Lo usan
`SaldoBanco` (§1.3, solo los 3 bancos reales) y `Transaccion` (§1.5), cuyo campo
`banco` admite además `manual` para las transacciones registradas a mano (F-04)."""

from enum import StrEnum


class Banco(StrEnum):
    BANCOLOMBIA = "bancolombia"
    BBVA = "bbva"
    GLOBAL66 = "global66"
    MANUAL = "manual"  # solo Transaccion §1.5 (id_banco 'MAN-'+ULID); no es banco real
```

## 7. Tests (código real)

### `backend/tests/test_bank_parsers.py`

```python
# backend/tests/test_bank_parsers.py
"""Parsers bancarios (Spec §1.5, portados de SISMO v2 y adaptados a COMPAS).

Cubre las reglas innegociables de CLAUDE.md:
  - Regla 1: montos = Decimal, NUNCA float.
  - Regla 7: los parsers transforman, no interpretan → fila ambigua = error
    acumulado en el resultado, jamás adivinado ni tragado en silencio.
  - Regla 7: Global66 conserva `moneda_original` + `tasa_cambio`.

COMPAS solo opera 3 bancos (enum `Banco`): Bancolombia, BBVA, Global66.
Fixtures sintéticos (openpyxl) — jamás datos reales en el repo.
"""

from datetime import date
from decimal import Decimal

import openpyxl
import pytest
from app.core.time import now_bogota
from app.domain.bancos import Banco
from app.parsers.bank_parsers import (
    ErrorFila,
    MovimientoBancario,
    ResultadoParseo,
    TipoMovimiento,
    detectar_banco,
    parse_bancolombia,
    parse_bbva,
    parse_extracto,
    parse_global66,
)
from pydantic import ValidationError

# ── Helpers de fixtures (estructura real de cada banco) ────────────────


def _crear_bancolombia(path, filas):
    """Bancolombia: hoja 'Extracto', headers fila 15, datos fila 16+.
    `filas` = lista de (fecha_str_d/m, descripcion, valor)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extracto"
    for i, h in enumerate(["FECHA", "DESCRIPCIÓN", "VALOR"], start=1):
        ws.cell(row=15, column=i, value=h)
    for off, (f, d, v) in enumerate(filas):
        ws.cell(row=16 + off, column=1, value=f)
        ws.cell(row=16 + off, column=2, value=d)
        ws.cell(row=16 + off, column=3, value=v)
    wb.save(str(path))
    wb.close()


def _crear_bbva(path, filas):
    """BBVA: hoja activa, headers fila 14, datos fila 15+.
    `filas` = lista de (fecha_str_d-m-Y, concepto, importe)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, h in enumerate(["FECHA DE OPERACIÓN", "CONCEPTO", "IMPORTE"], start=1):
        ws.cell(row=14, column=i, value=h)
    for off, (f, d, v) in enumerate(filas):
        ws.cell(row=15 + off, column=1, value=f)
        ws.cell(row=15 + off, column=2, value=d)
        ws.cell(row=15 + off, column=3, value=v)
    wb.save(str(path))
    wb.close()


def _crear_global66(path, filas):
    """Global66: hoja 'Movimientos de cuenta COP', headers fila 4, datos fila 5+.
    `filas` = lista de 14 columnas (A..N)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimientos de cuenta COP"
    ws.cell(row=1, column=1, value="Movimientos de cuenta COP")
    headers = [
        "Tipo transaccion", "Fecha", "Monto debitado", "Monto acreditado",
        "E", "F", "G", "Nombre tercero", "DNI tercero", "J", "K", "L",
        "ID transaccion", "Comentario",
    ]
    for i, h in enumerate(headers, start=1):
        ws.cell(row=4, column=i, value=h)
    for off, fila in enumerate(filas):
        for i, val in enumerate(fila, start=1):
            ws.cell(row=5 + off, column=i, value=val)
    wb.save(str(path))
    wb.close()


def _g66_fila(tipo="Debito", fecha="2026-03-15 10:30:00", debito=None,
              credito=None, tercero="TERCERO SA", ref="TXN-001", com="COMENTARIO"):
    return [tipo, fecha, debito, credito, None, None, None, tercero,
            "900123456", None, None, None, ref, com]


# ── Detección de banco ─────────────────────────────────────────────────


class TestDeteccion:
    def test_detecta_bancolombia(self, tmp_path):
        p = tmp_path / "b.xlsx"
        _crear_bancolombia(p, [])
        assert detectar_banco(str(p)) is Banco.BANCOLOMBIA

    def test_detecta_bbva(self, tmp_path):
        p = tmp_path / "v.xlsx"
        _crear_bbva(p, [])
        assert detectar_banco(str(p)) is Banco.BBVA

    def test_detecta_global66(self, tmp_path):
        p = tmp_path / "g.xlsx"
        _crear_global66(p, [])
        assert detectar_banco(str(p)) is Banco.GLOBAL66

    def test_formato_no_soportado_lanza_error(self, tmp_path):
        # COMPAS no soporta PDF/Nequi/Davivienda: debe fallar explícito, no adivinar.
        p = tmp_path / "x.pdf"
        p.write_bytes(b"%PDF-1.4 fake")
        with pytest.raises(ValueError):
            detectar_banco(str(p))


# ── Regla 1: Decimal, nunca float ────────────────────────────────────────


class TestReglaDecimal:
    def test_monto_parseado_es_decimal(self, tmp_path):
        p = tmp_path / "b.xlsx"
        _crear_bancolombia(p, [("15/03", "PAGO", -50000)])
        res = parse_bancolombia(str(p))
        m = res.movimientos[0]
        assert isinstance(m.monto, Decimal)
        assert not isinstance(m.monto, float)

    def test_modelo_rechaza_monto_float(self):
        # El tipo Money debe rechazar float en la construcción del modelo (regla 1).
        with pytest.raises(ValidationError):
            MovimientoBancario(
                fecha=date(2026, 3, 15),
                descripcion="X",
                monto=50000.0,  # float → prohibido
                tipo=TipoMovimiento.DEBITO,
                banco=Banco.BANCOLOMBIA,
            )


# ── Bancolombia ──────────────────────────────────────────────────────────


class TestBancolombia:
    def test_debito_y_credito(self, tmp_path):
        p = tmp_path / "b.xlsx"
        _crear_bancolombia(p, [
            ("15/03", "COMPRA", -50000),
            ("16/03", "ABONO", 120000),
        ])
        res = parse_bancolombia(str(p))
        assert isinstance(res, ResultadoParseo)
        assert res.errores == []
        anio = now_bogota().year
        deb, cred = res.movimientos
        assert deb.tipo is TipoMovimiento.DEBITO
        assert deb.monto == Decimal("50000")
        assert deb.fecha == date(anio, 3, 15)
        assert deb.banco is Banco.BANCOLOMBIA
        assert cred.tipo is TipoMovimiento.CREDITO
        assert cred.monto == Decimal("120000")

    def test_fila_totalmente_vacia_se_omite(self, tmp_path):
        p = tmp_path / "b.xlsx"
        _crear_bancolombia(p, [
            (None, None, None),
            ("17/03", "PAGO", -3000),
        ])
        res = parse_bancolombia(str(p))
        assert len(res.movimientos) == 1
        assert res.errores == []

    def test_monto_invalido_va_a_errores(self, tmp_path):
        # Regla 7: valor ambiguo NO se adivina como 0 ni se traga → error de fila.
        p = tmp_path / "b.xlsx"
        _crear_bancolombia(p, [("18/03", "RARO", "N/A")])
        res = parse_bancolombia(str(p))
        assert res.movimientos == []
        assert len(res.errores) == 1
        assert isinstance(res.errores[0], ErrorFila)
        assert res.errores[0].fila == 16

    def test_fecha_invalida_va_a_errores(self, tmp_path):
        p = tmp_path / "b.xlsx"
        _crear_bancolombia(p, [("nn/nn", "MALA FECHA", -1000)])
        res = parse_bancolombia(str(p))
        assert res.movimientos == []
        assert len(res.errores) == 1


# ── BBVA ─────────────────────────────────────────────────────────────────


class TestBBVA:
    def test_parse_basico(self, tmp_path):
        p = tmp_path / "v.xlsx"
        _crear_bbva(p, [
            ("15-03-2026", "RETIRO", -75000),
            ("16-03-2026", "NOMINA", 900000),
        ])
        res = parse_bbva(str(p))
        assert res.errores == []
        deb, cred = res.movimientos
        assert deb.tipo is TipoMovimiento.DEBITO
        assert deb.monto == Decimal("75000")
        assert deb.fecha == date(2026, 3, 15)
        assert deb.banco is Banco.BBVA
        assert cred.tipo is TipoMovimiento.CREDITO


# ── Global66 (con moneda_original + tasa_cambio, regla 7) ─────────────────


class TestGlobal66:
    def test_egreso_columna_debito(self, tmp_path):
        p = tmp_path / "g.xlsx"
        _crear_global66(p, [_g66_fila(
            tipo="Debito", debito=150000.0, ref="TXN-001", com="ALMUERZO",
            tercero="RESTAURANTE XYZ")])
        res = parse_global66(str(p))
        m = res.movimientos[0]
        assert m.tipo is TipoMovimiento.DEBITO
        assert m.monto == Decimal("150000")
        assert m.fecha == date(2026, 3, 15)
        assert m.banco is Banco.GLOBAL66
        assert m.referencia == "TXN-001"
        assert "ALMUERZO" in m.descripcion
        assert "RESTAURANTE XYZ" in m.descripcion

    def test_ingreso_columna_credito(self, tmp_path):
        p = tmp_path / "g.xlsx"
        _crear_global66(p, [_g66_fila(
            tipo="Abono", debito=None, credito=2500000.0, ref="TXN-002")])
        res = parse_global66(str(p))
        m = res.movimientos[0]
        assert m.tipo is TipoMovimiento.CREDITO
        assert m.monto == Decimal("2500000")
        assert m.referencia == "TXN-002"

    def test_conserva_moneda_y_tasa(self, tmp_path):
        # Regla 7: hoja COP -> moneda_original=COP, tasa_cambio=1 (hecho, no adivinado).
        p = tmp_path / "g.xlsx"
        _crear_global66(p, [_g66_fila(debito=5000.0)])
        m = parse_global66(str(p)).movimientos[0]
        assert m.moneda_original == "COP"
        assert m.tasa_cambio == Decimal("1")
        assert isinstance(m.tasa_cambio, Decimal)

    def test_omite_filas_sin_valor(self, tmp_path):
        p = tmp_path / "g.xlsx"
        _crear_global66(p, [
            _g66_fila(tipo="GMF", debito=None, credito=None, ref="TXN-VACIO"),
            _g66_fila(tipo="Debito", debito=5000.0, ref="TXN-OK"),
        ])
        res = parse_global66(str(p))
        assert len(res.movimientos) == 1
        assert res.movimientos[0].referencia == "TXN-OK"


# ── Dispatcher ───────────────────────────────────────────────────────────


class TestParseExtracto:
    def test_autodetecta_y_rutea(self, tmp_path):
        p = tmp_path / "g.xlsx"
        _crear_global66(p, [_g66_fila(debito=1000.0)])
        res = parse_extracto(str(p))
        assert res.banco is Banco.GLOBAL66
        assert len(res.movimientos) == 1
```

### `backend/tests/test_transaccion.py`

```python
# backend/tests/test_transaccion.py
"""Transaccion (Spec §1.5) + derivación de id_banco + mapper desde el parser.

Reglas cubiertas:
  - Regla 1: `valor` es Decimal (rechaza float), > 0 (el signo lo da tipo_flujo).
  - Regla 5: `id_banco` determinista para dedup — mismo movimiento → mismo id
    (dedup de solape); manual usa 'MAN-'+ULID (feature aparte).
  - Regla 7: Global66 conserva moneda/tasa; el id de Global66 es su referencia nativa.
  - Regla 3: schema strict, sin campos extra.

Parte pura (sin Mongo): modelo, `derivar_id_banco`, mapper. El comportamiento del
índice único parcial y la transacción multi-doc del flujo de carga se prueban en
tests marcados @requires_real_mongo (Incremento 2).
"""

from datetime import date
from decimal import Decimal

import pytest
from app.cargas.mapper import movimiento_a_transaccion
from app.domain.bancos import Banco
from app.domain.rubro import TipoFlujo
from app.domain.transaccion import (
    TRANSACCIONES_COLLECTION,
    Transaccion,
    derivar_id_banco,
)
from app.parsers.bank_parsers import MovimientoBancario, TipoMovimiento
from beanie import PydanticObjectId
from pydantic import ValidationError

_RUBRO = PydanticObjectId()
_MES = PydanticObjectId()


def _tx(**over):
    base = dict(
        fecha="2026-03-15",
        descripcion="PAGO PROVEEDOR",
        valor=Decimal("50000"),
        tipo_flujo=TipoFlujo.EGRESO,
        rubro_id=_RUBRO,
        mes_id=_MES,
        banco=Banco.BANCOLOMBIA,
        id_banco="abc123",
    )
    base.update(over)
    return Transaccion(**base)


# ── Modelo Transaccion ─────────────────────────────────────────────────


class TestModelo:
    def test_construccion_valida(self):
        t = _tx()
        assert t.valor == Decimal("50000")
        assert t.tipo_flujo is TipoFlujo.EGRESO
        assert t.tardia is False
        assert Transaccion.Settings.name == TRANSACCIONES_COLLECTION

    def test_valor_debe_ser_decimal_no_float(self):
        with pytest.raises(ValidationError):
            _tx(valor=50000.0)

    def test_valor_debe_ser_positivo(self):
        with pytest.raises(ValidationError):
            _tx(valor=Decimal("0"))
        with pytest.raises(ValidationError):
            _tx(valor=Decimal("-10"))

    def test_fecha_formato_invalido_falla(self):
        with pytest.raises(ValidationError):
            _tx(fecha="15/03/2026")

    def test_banco_manual_permitido(self):
        t = _tx(banco=Banco.MANUAL, id_banco="MAN-01HImanualULID")
        assert t.banco is Banco.MANUAL

    def test_rechaza_campo_extra(self):
        with pytest.raises(ValidationError):
            _tx(inventado="x")

    def test_id_banco_maximo_40(self):
        with pytest.raises(ValidationError):
            _tx(id_banco="x" * 41)

    def test_indice_unico_parcial_declarado(self):
        # Regla 5: (banco, id_banco) único con partialFilterExpression string.
        idx = {i.document["name"]: i.document for i in Transaccion.Settings.indexes}
        assert "banco_idbanco_unico" in idx
        u = idx["banco_idbanco_unico"]
        assert u.get("unique") is True
        assert u["partialFilterExpression"] == {"id_banco": {"$type": "string"}}


# ── derivar_id_banco ─────────────────────────────────────────────────────


class TestDerivarIdBanco:
    def test_global66_usa_referencia_nativa(self):
        idb = derivar_id_banco(
            banco=Banco.GLOBAL66, fecha="2026-03-15", descripcion="X",
            valor=Decimal("1000"), tipo_flujo=TipoFlujo.EGRESO, referencia="TXN-002",
        )
        assert idb == "TXN-002"

    def test_bancolombia_es_huella_determinista(self):
        args = dict(
            banco=Banco.BANCOLOMBIA, fecha="2026-03-15", descripcion="COMPRA",
            valor=Decimal("50000"), tipo_flujo=TipoFlujo.EGRESO,
        )
        a = derivar_id_banco(**args)
        b = derivar_id_banco(**args)
        assert a == b  # determinista → dedup de solape
        assert len(a) <= 40 and a.isalnum()

    def test_huella_cambia_con_el_monto(self):
        base = dict(
            banco=Banco.BBVA, fecha="2026-03-15", descripcion="X",
            tipo_flujo=TipoFlujo.EGRESO,
        )
        assert derivar_id_banco(valor=Decimal("100"), **base) != derivar_id_banco(
            valor=Decimal("200"), **base
        )

    def test_huella_cambia_con_el_banco(self):
        base = dict(
            fecha="2026-03-15", descripcion="X", valor=Decimal("100"),
            tipo_flujo=TipoFlujo.EGRESO,
        )
        assert derivar_id_banco(banco=Banco.BANCOLOMBIA, **base) != derivar_id_banco(
            banco=Banco.BBVA, **base
        )


# ── mapper MovimientoBancario → Transaccion ──────────────────────────────


def _mov(**over):
    base = dict(
        fecha=date(2026, 3, 15),
        descripcion="COMPRA",
        monto=Decimal("50000"),
        tipo=TipoMovimiento.DEBITO,
        banco=Banco.BANCOLOMBIA,
    )
    base.update(over)
    return MovimientoBancario(**base)


class TestMapper:
    def test_debito_mapea_a_egreso(self):
        t = movimiento_a_transaccion(_mov(tipo=TipoMovimiento.DEBITO),
                                     rubro_id=_RUBRO, mes_id=_MES)
        assert t.tipo_flujo is TipoFlujo.EGRESO
        assert t.valor == Decimal("50000")  # magnitud positiva
        assert t.fecha == "2026-03-15"  # date → string YYYY-MM-DD
        assert t.rubro_id == _RUBRO
        assert t.tardia is False

    def test_credito_mapea_a_ingreso(self):
        t = movimiento_a_transaccion(_mov(tipo=TipoMovimiento.CREDITO),
                                     rubro_id=_RUBRO, mes_id=_MES)
        assert t.tipo_flujo is TipoFlujo.INGRESO

    def test_global66_conserva_moneda_y_usa_referencia(self):
        mov = _mov(
            banco=Banco.GLOBAL66, tipo=TipoMovimiento.CREDITO,
            moneda_original="COP", tasa_cambio=Decimal("1"), referencia="TXN-77",
        )
        t = movimiento_a_transaccion(mov, rubro_id=_RUBRO, mes_id=_MES)
        assert t.moneda_original == "COP"
        assert t.tasa_cambio == Decimal("1")
        assert t.id_banco == "TXN-77"

    def test_bancolombia_id_banco_es_huella(self):
        t = movimiento_a_transaccion(_mov(), rubro_id=_RUBRO, mes_id=_MES)
        esperado = derivar_id_banco(
            banco=Banco.BANCOLOMBIA, fecha="2026-03-15", descripcion="COMPRA",
            valor=Decimal("50000"), tipo_flujo=TipoFlujo.EGRESO,
        )
        assert t.id_banco == esperado

    def test_propaga_carga_id(self):
        cid = PydanticObjectId()
        t = movimiento_a_transaccion(_mov(), rubro_id=_RUBRO, mes_id=_MES, carga_id=cid)
        assert t.carga_id == cid
```

### `backend/tests/test_transaccion_dedup.py`

```python
# backend/tests/test_transaccion_dedup.py
"""Deduplicación de Transaccion — SOLO contra Mongo REAL (regla 5, DoD F-04).

El índice ÚNICO PARCIAL (banco, id_banco) con partialFilterExpression
{id_banco:{$type:'string'}} NO lo soporta mongomock. Verifica:
  - '0 duplicados en solape': re-insertar el mismo (banco, id_banco) → DuplicateKey.
  - coexistencia de 2 manuales (F-04): id_banco 'MAN-' distinto, ambos entran.

Correr con:  pytest -m requires_real_mongo  (COMPAS_TEST_MONGO_URI a un Mongo real).
"""

import os
from decimal import Decimal

import pytest
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.rubro import TipoFlujo
from app.domain.transaccion import Transaccion
from beanie import PydanticObjectId, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

pytestmark = pytest.mark.requires_real_mongo


@pytest.fixture
async def real_db():
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    dbname = "compas_test_dedup"
    await client.drop_database(dbname)
    await init_beanie(database=client[dbname], document_models=DOMAIN_DOCUMENTS)
    yield client[dbname]
    await client.drop_database(dbname)
    client.close()


def _tx(id_banco: str, banco: Banco = Banco.BBVA) -> Transaccion:
    return Transaccion(
        fecha="2026-03-15",
        descripcion="MOVIMIENTO",
        valor=Decimal("50000"),
        tipo_flujo=TipoFlujo.EGRESO,
        rubro_id=PydanticObjectId(),
        mes_id=PydanticObjectId(),
        banco=banco,
        id_banco=id_banco,
    )


async def test_solape_no_duplica(real_db):
    """Mismo (banco, id_banco) dos veces → el 2º lanza DuplicateKeyError."""
    await _tx("HUELLA-1").insert()
    with pytest.raises(DuplicateKeyError):
        await _tx("HUELLA-1").insert()


async def test_mismo_banco_distinto_idbanco_ok(real_db):
    await _tx("HUELLA-A").insert()
    await _tx("HUELLA-B").insert()  # no colisiona


async def test_dos_manuales_coexisten(real_db):
    """F-04: dos transacciones manuales del mismo día no chocan (id_banco distinto)."""
    await _tx("MAN-01HAAAAAAAAAAAAAAAAAAAAA", banco=Banco.MANUAL).insert()
    await _tx("MAN-01HBBBBBBBBBBBBBBBBBBBBB", banco=Banco.MANUAL).insert()
```

### `backend/tests/test_carga.py`

```python
# backend/tests/test_carga.py
"""CargaBancaria (Spec §1.6) + servicio de carga.

MARCADO PARA AUDITORÍA KIMI (flujo crítico: cargas bancarias).

Decisión de contrato registrada: el §1.6 especifica `insertMany ordered=False`
contando duplicados por DuplicateKeyError (idempotente, NO transaccional). La regla 8
lista "finalización de carga" como transacción multi-doc, PERO es incompatible con el
conteo-y-continúa del §1.6 (una transacción abortaría en el 1er duplicado). Se sigue el
§1.6 (data dictionary manda) → pendiente nota/CR y gate Kimi.

Los tests del servicio necesitan Mongo real (índice único parcial + insertMany dedup):
@requires_real_mongo. Los del modelo son puros.
"""

import os
from decimal import Decimal

import openpyxl
import pytest
from app.audit import service as audit_service
from app.audit.events import AuditEvento
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.carga import CARGAS_COLLECTION, CargaBancaria, EstadoCarga
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from beanie import PydanticObjectId, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

# ── Modelo (puro) ─────────────────────────────────────────────────────────


def _carga(**over) -> CargaBancaria:
    base = dict(
        banco=Banco.BBVA,
        archivo_nombre="extracto.xlsx",
        archivo_hash="a" * 64,
        usuario_id=PydanticObjectId(),
    )
    base.update(over)
    return CargaBancaria(**base)


class TestModeloCarga:
    def test_estado_inicial_procesando(self):
        c = _carga()
        assert c.estado is EstadoCarga.PROCESANDO
        assert c.total_filas == 0 and c.nuevas == 0 and c.duplicadas == 0
        assert CargaBancaria.Settings.name == CARGAS_COLLECTION

    def test_banco_manual_no_es_carga(self):
        # Una carga proviene SIEMPRE de un archivo de banco real, nunca 'manual'.
        with pytest.raises(ValidationError):
            _carga(banco=Banco.MANUAL)

    def test_hash_debe_ser_sha256_hex(self):
        with pytest.raises(ValidationError):
            _carga(archivo_hash="no-es-hash")

    def test_rechaza_campo_extra(self):
        with pytest.raises(ValidationError):
            _carga(inventado="x")


# ── Helper de fixture xlsx (BBVA, fechas explícitas) ─────────────────────


def _crear_bbva(path, filas):
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, h in enumerate(["FECHA DE OPERACIÓN", "CONCEPTO", "IMPORTE"], start=1):
        ws.cell(row=14, column=i, value=h)
    for off, (f, d, v) in enumerate(filas):
        ws.cell(row=15 + off, column=1, value=f)
        ws.cell(row=15 + off, column=2, value=d)
        ws.cell(row=15 + off, column=3, value=v)
    wb.save(str(path))
    wb.close()


# ── Servicio (Mongo real) ────────────────────────────────────────────────


@pytest.mark.requires_real_mongo
class TestServicioCarga:
    @pytest.fixture
    async def entorno(self):
        uri = os.environ.get("COMPAS_TEST_MONGO_URI")
        if not uri:
            pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
        client = AsyncIOMotorClient(uri, tz_aware=True)
        dbname = "compas_test_carga"
        await client.drop_database(dbname)
        db = client[dbname]
        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
        audit_service.configure_audit(client, dbname)
        # Semillas mínimas: rubro 'Por clasificar' + MesControl de marzo 2026.
        await Rubro(
            grupo="otros", nombre="Por clasificar", orden=99, es_sistema=True
        ).insert()
        await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()
        yield db
        audit_service.reset_audit()
        await client.drop_database(dbname)
        client.close()

    async def _procesar(self, tmp_path, filas, nombre="ext.xlsx"):
        from app.cargas.service import procesar_carga

        p = tmp_path / nombre
        _crear_bbva(p, filas)
        return await procesar_carga(
            banco=Banco.BBVA,
            archivo_path=str(p),
            archivo_nombre=nombre,
            usuario_id=PydanticObjectId(),
        )

    async def test_completada_inserta_transacciones(self, entorno, tmp_path):
        carga = await self._procesar(tmp_path, [
            ("15-03-2026", "COMPRA", -50000),
            ("16-03-2026", "NOMINA", 900000),
        ])
        assert carga.estado is EstadoCarga.COMPLETADA
        assert carga.nuevas == 2
        assert carga.duplicadas == 0
        assert await Transaccion.find(Transaccion.carga_id == carga.id).count() == 2

    async def test_solape_no_duplica(self, entorno, tmp_path):
        # 1ª carga: 1 movimiento. 2ª carga (archivo distinto): el mismo + 1 nuevo.
        await self._procesar(tmp_path, [("15-03-2026", "COMPRA", -50000)], "a.xlsx")
        carga2 = await self._procesar(tmp_path, [
            ("15-03-2026", "COMPRA", -50000),   # solape → duplicado
            ("17-03-2026", "PAGO", -3000),      # nuevo
        ], "b.xlsx")
        assert carga2.nuevas == 1
        assert carga2.duplicadas == 1

    async def test_archivo_completado_se_rechaza(self, entorno, tmp_path):
        from app.cargas.service import CargaDuplicadaError, procesar_carga

        p = tmp_path / "dup.xlsx"
        _crear_bbva(p, [("15-03-2026", "COMPRA", -50000)])
        kw = dict(banco=Banco.BBVA, archivo_path=str(p), archivo_nombre="dup.xlsx",
                  usuario_id=PydanticObjectId())
        await procesar_carga(**kw)
        with pytest.raises(CargaDuplicadaError):
            await procesar_carga(**kw)  # mismo hash, ya completada → F-02

    async def test_movimiento_sin_mes_va_a_errores(self, entorno, tmp_path):
        # Abril no tiene MesControl → ese movimiento no se inserta, cuenta como error.
        carga = await self._procesar(tmp_path, [
            ("15-03-2026", "OK MARZO", -1000),
            ("15-04-2026", "SIN MES ABRIL", -2000),
        ])
        assert carga.nuevas == 1
        assert carga.errores == 1
        assert any("2026-04" in e.motivo for e in carga.errores_detalle)

    async def test_emite_evento_carga_completada(self, entorno, tmp_path):
        carga = await self._procesar(tmp_path, [("15-03-2026", "X", -1000)])
        col = entorno["audit_log"]
        doc = await col.find_one({"evento": AuditEvento.carga_completada.value})
        assert doc is not None
        assert doc["entidad_id"] == str(carga.id)
```
