# FABS · Reporte a inversionistas (inc6 · #3) · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un endpoint a demanda que genera un `.docx` formal para inversionistas — narrativa de FABS + cifras deterministas de COMPAS + una gráfica embebida del rumbo de caja — que el CEO descarga, revisa y envía por fuera.

**Architecture:** `cfo/reporte/` — `modelos.py` (schemas), `datos.py` (orquestación: lee servicios vigentes + narra vía consultar), `grafica.py` (matplotlib Agg → PNG, puro), `documento.py` (python-docx → bytes, puro), y el endpoint `POST /cfo/reporte-inversionistas` (RBAC export:reportes, descarga). CERO cambios al motor.

**Tech Stack:** FastAPI + Beanie/Motor + Pydantic strict. Deps NUEVAS runtime: `python-docx`, `matplotlib`. Tests: pytest + mongomock.

**Spec:** `docs/superpowers/specs/2026-09-08-fabs-reporte-inversionistas-design.md` (léelo junto a este plan).

## Global Constraints

- **Dinero = `Decimal`** backend, string en la API/tablas (`money_str`); formateo es-CO; **sin float en cálculo ni display de dinero** (regla 1). **Excepción explícita y única:** la gráfica convierte los Decimal ya calculados a `float` SOLO para posicionar puntos/pixeles (geometría del render matplotlib) — no es cálculo ni display de dinero; las cifras autoritativas viven en las tablas del .docx como `money_str`. Documentar el porqué en el código.
- **TZ** `now_bogota()`/`today_bogota()`; `periodo` `YYYY-MM`.
- **`app/proyeccion/motor.py` y `presupuesto/motor.py`: 0 diffs** (solo se LEE).
- **S1:** `cfo/reporte/grafica.py` y `documento.py` son transformaciones puras (NO importan motor/domain/servicios — reciben datos, devuelven bytes). `datos.py` es orquestación (lee servicios). `cfo/calc` intacto; `test_s1_aislamiento` verde.
- **Anti-alucinación:** las cifras salen de servicios de COMPAS (`money_str`), en tablas; la narrativa (resumen ejecutivo) vía `consultar` (verifica antes de sustituir; el modelo nunca escribe un número). El CEO revisa antes de enviar.
- **RBAC** `require_permission("export:reportes")` (financiero/directivo/admin, ya existe — sin permiso nuevo); guard 404 si `not cfo_enabled()`.
- **matplotlib import perezoso** (dentro de la función de render), backend `Agg` — no cargar al arrancar el web.

---

### Task 1: Deps + `modelos.py` + `documento.armar_docx` (python-docx, puro)

**Files:**
- Modify: `backend/requirements.txt` (add `python-docx`, `matplotlib`)
- Create: `backend/app/cfo/reporte/__init__.py`, `backend/app/cfo/reporte/modelos.py`, `backend/app/cfo/reporte/documento.py`
- Test: `backend/tests/cfo/reporte/test_documento.py` (nuevo, con `__init__.py`)

**Interfaces:**
- Produces: `Cifra`, `Seccion`, `RumboSerie`, `DatosReporte` (Pydantic strict); `armar_docx(datos: DatosReporte, png_rumbo: bytes | None) -> bytes`.

- [ ] **Step 1: Añadir deps + escribir el test**

`backend/requirements.txt`: agregar `python-docx==1.1.2` y `matplotlib==3.9.2` (o las últimas estables). Correr `pip install -r requirements.txt`.

```python
# backend/tests/cfo/reporte/test_documento.py
from io import BytesIO
from docx import Document
from app.cfo.reporte.modelos import Cifra, DatosReporte, RumboSerie, Seccion
from app.cfo.reporte.documento import armar_docx


def _datos():
    return DatosReporte(
        periodo="2026-09",
        resumen_ejecutivo="La caja disponible es $5.000.000 y el piso proyectado cruza el umbral en abril-2027.",
        secciones=[
            Seccion(titulo="Caja y rumbo al umbral", cifras=[
                Cifra(etiqueta="Caja disponible hoy", valor="$5.000.000"),
                Cifra(etiqueta="Piso proyectado", valor="$1.200.000"),
            ]),
            Seccion(titulo="Ventas / colocación", cifras=[Cifra(etiqueta="Mix Raider", valor="45,0%")]),
        ],
        rumbo=RumboSerie(meses=["2026-09", "2026-10"], caja=["5000000", "4200000"],
                         caja_minima="1000000", caja_atencion="3000000"),
    )


def test_armar_docx_valido_con_secciones_y_grafica():
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64  # placeholder bytes (no se valida como imagen real aquí)
    data = armar_docx(_datos(), png_rumbo=None)  # sin imagen para no exigir un PNG válido
    assert isinstance(data, bytes) and len(data) > 0
    doc = Document(BytesIO(data))  # round-trip: abre
    textos = [p.text for p in doc.paragraphs]
    assert any("Reporte a inversionistas" in t for t in textos)
    assert any("Resumen ejecutivo" in t for t in textos)
    assert any("Caja y rumbo al umbral" in t for t in textos)
    # las cifras van en tablas
    celdas = [c.text for tbl in doc.tables for row in tbl.rows for c in row.cells]
    assert "Caja disponible hoy" in celdas and "$5.000.000" in celdas


def test_armar_docx_embebe_la_grafica_si_hay_png(tmp_path):
    # PNG real mínimo 1x1 (para que add_picture no falle)
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    data = armar_docx(_datos(), png_rumbo=png)
    doc = Document(BytesIO(data))
    assert len(doc.inline_shapes) >= 1  # la imagen quedó embebida
```

- [ ] **Step 2: Correr — debe fallar** (`ModuleNotFoundError` docx / no existe armar_docx)

Run (desde `backend/`): `python -m pytest tests/cfo/reporte/test_documento.py -q`
Expected: FAIL.

- [ ] **Step 3: `modelos.py`**

```python
# backend/app/cfo/reporte/modelos.py
from pydantic import BaseModel, ConfigDict


class Cifra(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    etiqueta: str
    valor: str  # money_str es-CO o texto; NUNCA number


class Seccion(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    titulo: str
    cifras: list[Cifra]


class RumboSerie(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    meses: list[str]
    caja: list[str]  # money_str por mes (para la gráfica)
    caja_minima: str
    caja_atencion: str | None = None


class DatosReporte(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    periodo: str  # 'YYYY-MM'
    resumen_ejecutivo: str  # narrado por FABS (ya verificado/sustituido)
    secciones: list[Seccion]
    rumbo: RumboSerie | None = None  # None ⇒ sin proyección ⇒ sin gráfica
```

- [ ] **Step 4: `documento.py`** (puro — datos+png in, bytes out; NO importa servicios/domain)

```python
# backend/app/cfo/reporte/documento.py
"""FABS · ensambla el .docx del reporte a inversionistas (python-docx). PURO: recibe
DatosReporte + PNG y devuelve los bytes del documento; no lee servicios ni dominio (S1)."""

from io import BytesIO

from docx import Document
from docx.shared import Inches

from app.cfo.reporte.modelos import DatosReporte


def armar_docx(datos: DatosReporte, png_rumbo: bytes | None) -> bytes:
    doc = Document()
    doc.add_heading(f"RODDOS S.A.S. — Reporte a inversionistas — {datos.periodo}", level=0)
    doc.add_heading("Resumen ejecutivo", level=1)
    doc.add_paragraph(datos.resumen_ejecutivo)
    if png_rumbo:
        doc.add_picture(BytesIO(png_rumbo), width=Inches(6.0))
    for sec in datos.secciones:
        doc.add_heading(sec.titulo, level=1)
        if sec.cifras:
            tabla = doc.add_table(rows=0, cols=2)
            tabla.style = "Light Grid Accent 1"
            for c in sec.cifras:
                fila = tabla.add_row().cells
                fila[0].text = c.etiqueta
                fila[1].text = c.valor
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 5: Verde** — `python -m pytest tests/cfo/reporte/test_documento.py -q`

- [ ] **Step 6: Commit** — `feat(cfo): reporte a inversionistas — modelos + armar_docx (python-docx) + deps`

---

### Task 2: `grafica.render_rumbo` (matplotlib Agg, puro)

**Files:**
- Create: `backend/app/cfo/reporte/grafica.py`
- Test: `backend/tests/cfo/reporte/test_grafica.py`

**Interfaces:**
- Consumes: `RumboSerie` (Task 1).
- Produces: `render_rumbo(rumbo: RumboSerie) -> bytes` (PNG).

- [ ] **Step 1: Test**

```python
# backend/tests/cfo/reporte/test_grafica.py
from app.cfo.reporte.modelos import RumboSerie
from app.cfo.reporte.grafica import render_rumbo


def test_render_rumbo_devuelve_png():
    r = RumboSerie(meses=["2026-09", "2026-10", "2026-11"],
                   caja=["5000000", "4200000", "3100000"],
                   caja_minima="1000000", caja_atencion="3000000")
    png = render_rumbo(r)
    assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"  # magic PNG
    assert len(png) > 100
```

- [ ] **Step 2: Correr — falla**

- [ ] **Step 3: `grafica.py`**

```python
# backend/app/cfo/reporte/grafica.py
"""FABS · gráfica del rumbo de caja para el reporte (matplotlib, backend Agg no-interactivo).
PURO: RumboSerie in, PNG bytes out. matplotlib se importa PEREZOSAMENTE (es pesada; no
cargarla al arrancar el web). NOTA regla 1: los Decimal ya calculados por COMPAS se pasan a
float SOLO para posicionar los puntos de la curva (geometría del render) — no es cálculo ni
display de dinero; las cifras autoritativas van en las tablas del .docx como money_str."""

from decimal import Decimal
from io import BytesIO

from app.cfo.reporte.modelos import RumboSerie


def render_rumbo(rumbo: RumboSerie) -> bytes:
    import matplotlib

    matplotlib.use("Agg")  # server-side, sin display
    import matplotlib.pyplot as plt

    xs = list(range(len(rumbo.meses)))
    ys = [float(Decimal(v)) for v in rumbo.caja]  # float SOLO para geometría (ver docstring)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(xs, ys, marker="o", label="Caja proyectada")
    ax.axhline(float(Decimal(rumbo.caja_minima)), linestyle="--", color="#b91c1c", label="Umbral crítico")
    if rumbo.caja_atencion is not None:
        ax.axhline(float(Decimal(rumbo.caja_atencion)), linestyle=":", color="#b45309", label="Umbral de atención")
    ax.set_xticks(xs)
    ax.set_xticklabels(rumbo.meses, rotation=45, ha="right")
    ax.set_ylabel("Caja (COP)")
    ax.set_title("Rumbo de caja hacia el umbral")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()
```

- [ ] **Step 4: Verde** — `python -m pytest tests/cfo/reporte/test_grafica.py tests/cfo/test_s1_aislamiento.py -q`

- [ ] **Step 5: Commit** — `feat(cfo): reporte a inversionistas — grafica del rumbo (matplotlib Agg, puro)`

---

### Task 3: `datos.reunir_datos` (orquestación: servicios + narrativa)

**Files:**
- Create: `backend/app/cfo/reporte/datos.py`
- Test: `backend/tests/cfo/reporte/test_datos.py`

**Interfaces:**
- Consumes: `proyeccion.service.proyectar_vigente` (caja/piso/umbral/serie), `modelos_moto.service.mix_activos`, `proyeccion.service.composicion_gasto_real`, `presupuesto.service` (real vs presupuesto), `cfo.calc.iva`, `escenario.motos_para_evitar_umbral`, `servicio.consultar` (narrativa). READ the existing tool wrappers in `cfo/agente/tools.py` and `cfo/vigilante/iva.py` for the EXACT service calls/shapes — reuse them.
- Produces: `async reunir_datos(periodo: str | None) -> DatosReporte`.

- [ ] **Step 1: Test** (fakea `proyectar_vigente` + `consultar`; monkeypatch a nivel módulo)

```python
# backend/tests/cfo/reporte/test_datos.py
import pytest
from app.cfo.reporte import datos as D
from app.cfo.reporte.modelos import DatosReporte


@pytest.mark.asyncio
async def test_reunir_datos_arma_secciones_y_rumbo(monkeypatch):
    async def fake_proy(**k):
        return {"caja_minima": "1000000", "caja_atencion": "3000000", "piso_caja": "1200000",
                "meses": [{"mes": "2026-09", "caja": "5000000", "estado": "ok"},
                          {"mes": "2026-10", "caja": "4200000", "estado": "atencion"}]}
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)

    async def fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        from app.cfo.agente.modelos import RespuestaCFO, UsoLLM
        return RespuestaCFO(texto="Resumen narrado con $5.000.000.", abstuvo=False,
                            texto_crudo="Resumen narrado con [[x]].",
                            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1))
    monkeypatch.setattr(D.servicio, "consultar", fake_consultar)
    # las demás lecturas (mix/gasto/iva/motos) se fakean o se dejan abstenerse — el test
    # verifica la ESTRUCTURA + el rumbo + el resumen narrado.

    datos = await D.reunir_datos(periodo=None)
    assert isinstance(datos, DatosReporte)
    assert datos.rumbo is not None and datos.rumbo.caja_minima == "1000000"
    assert datos.rumbo.meses == ["2026-09", "2026-10"]
    assert "5.000.000" in datos.resumen_ejecutivo
    assert any(s.titulo.startswith("Caja") for s in datos.secciones)


@pytest.mark.asyncio
async def test_sin_proyeccion_abstiene_rumbo(monkeypatch):
    from app.proyeccion.service import ProyeccionError

    async def fake_proy(**k):
        raise ProyeccionError("sin config", 409)
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    async def fake_consultar(*a, **k):
        from app.cfo.agente.modelos import RespuestaCFO, UsoLLM
        return RespuestaCFO(texto="Sin proyección disponible.", abstuvo=True, texto_crudo="…",
                            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1))
    monkeypatch.setattr(D.servicio, "consultar", fake_consultar)

    datos = await D.reunir_datos(periodo=None)
    assert datos.rumbo is None  # sin proyección ⇒ sin serie ⇒ sin gráfica
```

- [ ] **Step 2: Correr — falla**

- [ ] **Step 3: `datos.py`** — implementa `reunir_datos`:
  - `periodo = periodo or now_bogota().strftime("%Y-%m")`.
  - Lee `proyectar_vigente(escenario="base", mes_inicio=(hoy.year, hoy.month), horizonte_meses=None)`; en `ProyeccionError` → `rumbo=None` y las secciones de caja dicen "sin datos".
  - **Rumbo:** de `proy["meses"]` → `RumboSerie(meses=[m["mes"]…], caja=[m["caja"]…], caja_minima=proy["caja_minima"], caja_atencion=proy["caja_atencion"])`.
  - **Secciones** (cifras `money_str`, reusando las lecturas de los tool wrappers): (1) Caja y rumbo (disponible hoy, piso, mes de quiebre, runway); (2) Ventas/colocación (mix + motos_para_evitar_umbral); (3) Gasto/eficiencia (composicion_gasto_real + real_vs_presupuesto); (4) Deuda/IVA. Cada lectura que falle/abstenga → una `Cifra("…","sin datos")`, no revienta.
  - **Resumen ejecutivo:** `resp = await consultar(_PROMPT_REPORTE(periodo), actor_id="reporte", cliente=crear_cliente())`; `resumen_ejecutivo = resp.texto` (ya verificado/sustituido). Prompt factual/conservador, pide citar cada cifra por token.
  - Devuelve `DatosReporte(...)`.

- [ ] **Step 4: Verde** — `python -m pytest tests/cfo/reporte/test_datos.py tests/cfo/test_s1_aislamiento.py -q`

- [ ] **Step 5: Commit** — `feat(cfo): reporte a inversionistas — reunir_datos (servicios vigentes + narrativa FABS)`

---

### Task 4: Endpoint `POST /cfo/reporte-inversionistas` (descarga .docx)

**Files:**
- Create: `backend/app/cfo/reporte/router.py` (o extender `cfo/router.py`)
- Modify: `backend/app/main.py` si hace falta montar el router (mira cómo se monta `cfo_router`)
- Test: `backend/tests/cfo/reporte/test_router_reporte.py`

**Interfaces:**
- Consumes: `reunir_datos` (T3), `render_rumbo` (T2), `armar_docx` (T1).
- Produces: `POST /api/v1/cfo/reporte-inversionistas` → descarga `.docx`.

- [ ] **Step 1: Test** (RBAC + 404 + media_type + Content-Disposition; fakea reunir_datos)

Cubrir: 401 sin token; 403 sin `export:reportes`; 404 con `cfo_enabled()` False; 200 con `export:reportes` → `media_type` de docx + header `Content-Disposition: attachment; filename="reporte-inversionistas-…docx"` + body bytes no vacío. Fakea `reunir_datos` para no depender de servicios/LLM; verifica que si `render_rumbo` lanza, el reporte sale igual sin gráfica (fail-soft).

- [ ] **Step 2–3: Implementar** el handler:
```python
@router.post("/reporte-inversionistas")
async def reporte_inversionistas(
    body: ReporteBody, user: User = Depends(require_permission("export:reportes"))
):
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    datos = await reunir_datos(body.periodo)
    png = None
    if datos.rumbo is not None:
        try:
            png = render_rumbo(datos.rumbo)
        except Exception:  # noqa: BLE001 — fail-soft: sin gráfica, no tumbar el reporte
            logger.exception("fallo al renderizar la gráfica del reporte")
    doc = armar_docx(datos, png)
    return Response(
        content=doc,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="reporte-inversionistas-{datos.periodo}.docx"'},
    )
```
`ReporteBody(BaseModel, strict, extra=forbid)`: `periodo: str | None = None`. Montar el router (mismo patrón condicional que `cfo_router` bajo `CFO_ENABLED`).

- [ ] **Step 4: Verde** — `python -m pytest tests/cfo/reporte tests/cfo -q`

- [ ] **Step 5: Commit** — `feat(cfo): endpoint POST /cfo/reporte-inversionistas (descarga .docx, RBAC export:reportes)`

---

### Task 5: Cierre — guardas + roadmap

**Files:**
- Modify: `docs/COMPAS_FABS_ROADMAP.md`

- [ ] **Step 1: Guardas.** Run:
```bash
git fetch origin -q
git diff --stat origin/main..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py && echo "motor 0 diffs OK"
cd backend && pip install -r requirements.txt >/dev/null 2>&1 && python -m pytest tests/cfo -q && python -m ruff check app/cfo && python -m pytest tests/cfo/test_s1_aislamiento.py -q && cd ..
```
Expected: motor 0 diffs; suites verdes; ruff limpio; S1 verde; `python-docx`+`matplotlib` en requirements.
- [ ] **Step 2: Roadmap** — entrada fechada 2026-09-08 del reporte a inversionistas (inc6 #3): endpoint a demanda que genera un `.docx` (5 secciones, recap+prospectivo, gráfica embebida matplotlib), cifras deterministas + narrativa FABS, RBAC export:reportes, el CEO revisa y envía por fuera; deps nuevas python-docx+matplotlib (import perezoso); gate = gate-waiver + GO CEO (NO afirmar Kimi). Con esto de inc6 solo queda #2 (escenarios conversacionales).
- [ ] **Step 3: Commit** — `docs(fabs): reporte a inversionistas — roadmap`.

---

## Self-Review

**1. Spec coverage:** §5.1 endpoint→T4; §5.2 datos→T3; §5.3 narrativa→T3 (consultar); §5.4 gráfica→T2; §5.5 documento→T1; §5.6 deps→T1; §6 anti-alucinación→T3 (consultar) + tablas money_str; §7 reglas→Global Constraints + T5; §8 casos borde→T3 (abstención) + T4 (fail-soft gráfica); §9 testing→cada task; §10 fuera de alcance→respetado. Cubierto.

**2. Placeholder scan:** T1/T2 traen el código real; T3 da la estructura + el shape de `proyectar_vigente` y remite a los tool wrappers reales para las demás lecturas (código existente, no placeholder); T4 trae el handler real.

**3. Type consistency:** `DatosReporte{periodo, resumen_ejecutivo, secciones:[Seccion{titulo,cifras:[Cifra{etiqueta,valor}]}], rumbo:RumboSerie|None}` idéntico en T1 (define+documento), T2 (grafica usa RumboSerie), T3 (datos produce), T4 (endpoint consume). `armar_docx(datos, png|None)` (T1) ← T4. `render_rumbo(rumbo)->bytes` (T2) ← T4. `reunir_datos(periodo)->DatosReporte` (T3) ← T4. RBAC `export:reportes` en T4. Consistente.
