# FABS · Chat embebido en COMPAS · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un panel de chat de FABS acoplable dentro de COMPAS, conversacional sobre el hilo compartido con Telegram, con scrollback cruzado completo.

**Architecture:** backend — `POST /api/v1/cfo` pasa a conversacional sobre `HiloCFO` (por `user_id`) + `GET /cfo/historial` sirve el scrollback; el hilo gana un log de display (`mostrado` por turno, retención 200). Frontend — un panel slide-over en el shell del cockpit, gateado por `cfo:consultar`.

**Tech Stack:** Backend FastAPI + Beanie/Motor + Pydantic strict. Frontend React 19 + Vite + TS + Tailwind. Tests: pytest + mongomock (backend), Vitest + RTL (frontend).

**Spec:** `docs/superpowers/specs/2026-08-30-fabs-chat-embebido-design.md` (léelo junto a este plan).

## Global Constraints

- **Dinero = string** en la API; el front NUNCA hace `Number` sobre montos (regla 1); el formato es-CO ya viene en el `texto`.
- **Pydantic strict** en todo schema nuevo. **TZ**: `ts` de turnos en UTC-aware (`now_utc().isoformat()`, mismo patrón que `actualizado_at`).
- **RBAC por dependencia** `require_permission("cfo:consultar")` en ambos endpoints (regla 9); front gateado por `useAuth().puede("cfo:consultar")`, derivado del config único.
- **`app/proyeccion/motor.py` y `presupuesto/motor.py`: 0 diffs** (el chat solo consume `consultar`).
- **Anti-alucinación:** el scrollback pinta `mostrado` (ya verificado/sustituido), nunca se re-verifica; turnos legacy sin `mostrado` se enmascaran, jamás se expone crudo con `[[tokens]]`. El re-alimentado al LLM sigue siendo el CRUDO (`contenido`).
- **El turno web NO toca `ultimo_update_id`/`ultimo_envio`** (estado de dedup de Telegram) — solo Telegram los setea.
- **Frontend:** tras tocar tipos compartidos, `npm run build` (tsc -b) debe pasar (no solo vitest) — el CI tipa los tests.

---

### Task 1: Backend — log de display en el hilo (mostrado/canal/ts + retención 200)

**Files:**
- Modify: `backend/app/cfo/telegram/hilos.py`
- Test: `backend/tests/cfo/telegram/test_hilos.py` (o el archivo de tests de hilos existente; si no existe, créalo)
- Modify (mantener verde): `backend/tests/cfo/telegram/test_webhook_publicar.py` / cualquier test que asserte la forma de `turnos`

**Interfaces:**
- Produces: `_MAX_TURNOS = 200`; `registrar_turno(user_id, pregunta, texto_crudo, update_id, envio)` (firma IGUAL, ahora guarda `mostrado`/`canal="telegram"`/`ts`); `registrar_turno_web(user_id, pregunta, texto_crudo, mostrado)`; `historial_para_display(hilo) -> list[dict]`. `historial_para_loop` SIN cambios (lee `contenido`).

- [ ] **Step 1: Escribir los tests**

```python
# backend/tests/cfo/telegram/test_hilos.py
import pytest
import pytest_asyncio
from app.cfo.telegram import hilos, repositorio
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_registrar_turno_web_guarda_mostrado_y_no_toca_dedup(db):
    # un turno de Telegram deja estado de dedup
    await hilos.registrar_turno("u1", "hola tg", "[[x]]", 55, "MOSTRADO TG")
    # un turno web NO debe pisar ultimo_update_id/ultimo_envio
    await hilos.registrar_turno_web("u1", "hola web", "[[y]]", "MOSTRADO WEB")
    hilo = await repositorio.obtener_hilo("u1")
    assert hilo.ultimo_update_id == 55  # intacto
    assert hilo.ultimo_envio == "MOSTRADO TG"  # intacto
    # 4 turnos, el último assistant es el web con su mostrado + canal
    ult = hilo.turnos[-1]
    assert ult["rol"] == "assistant" and ult["mostrado"] == "MOSTRADO WEB"
    assert ult["canal"] == "web" and ult["contenido"] == "[[y]]"
    tg_asst = hilo.turnos[1]
    assert tg_asst["canal"] == "telegram" and tg_asst["mostrado"] == "MOSTRADO TG"


@pytest.mark.asyncio
async def test_historial_para_display_enmascara_legacy(db):
    # sembrar un hilo con un turno assistant LEGACY (sin mostrado) + uno nuevo
    from app.cfo.telegram.modelos import HiloCFO
    from app.core.time import now_utc
    await repositorio.guardar_hilo(HiloCFO(
        user_id="u2",
        turnos=[
            {"rol": "user", "contenido": "q vieja"},  # legacy user (sin mostrado)
            {"rol": "assistant", "contenido": "[[caja_hoy]]"},  # legacy assistant sin mostrado
            {"rol": "user", "contenido": "q nueva", "mostrado": "q nueva", "canal": "web", "ts": "2026-08-30T00:00:00+00:00"},
            {"rol": "assistant", "contenido": "[[x]]", "mostrado": "$5.000.000 (al 2026-08-30)", "canal": "web", "ts": "2026-08-30T00:00:00+00:00"},
        ],
        actualizado_at=now_utc(),
    ))
    disp = hilos.historial_para_display(await repositorio.obtener_hilo("u2"))
    assert disp[0] == {"rol": "user", "texto": "q vieja", "canal": "desconocido", "ts": None}
    assert disp[1]["texto"] == "(respuesta anterior)"  # legacy assistant NO expone crudo
    assert "[[" not in disp[1]["texto"]
    assert disp[3]["texto"] == "$5.000.000 (al 2026-08-30)" and disp[3]["canal"] == "web"


@pytest.mark.asyncio
async def test_retencion_200(db):
    for i in range(150):  # 150 pares = 300 turnos → recorta a 200
        await hilos.registrar_turno_web("u3", f"q{i}", f"[[{i}]]", f"m{i}")
    hilo = await repositorio.obtener_hilo("u3")
    assert len(hilo.turnos) == 200
```

- [ ] **Step 2: Correr — debe fallar** (`registrar_turno_web` no existe)

Run: `python -m pytest tests/cfo/telegram/test_hilos.py -q`
Expected: FAIL.

- [ ] **Step 3: Editar `hilos.py`**

Cambiar `_MAX_TURNOS = 40` → `_MAX_TURNOS = 200`. Añadir el helper compartido y las dos funciones, y hacer que `registrar_turno` delegue:

```python
async def _append_turnos(
    user_id: str, pregunta: str, crudo: str, mostrado: str, canal: str,
    *, update_id: int | None = None, set_dedup: bool = False,
) -> None:
    """Arma los dos turnos (user + assistant) con display (`mostrado`/`canal`/`ts`) y
    persiste, recortando a _MAX_TURNOS. `set_dedup=True` (Telegram) actualiza el estado
    de dedup (`ultimo_update_id`/`ultimo_envio`); `set_dedup=False` (web) lo PRESERVA."""
    hilo = await repositorio.obtener_hilo(user_id)
    ts = now_utc().isoformat()
    turnos = (hilo.turnos if hilo else []) + [
        {"rol": "user", "contenido": pregunta, "mostrado": pregunta, "canal": canal, "ts": ts},
        {"rol": "assistant", "contenido": crudo, "mostrado": mostrado, "canal": canal, "ts": ts},
    ]
    turnos = turnos[-_MAX_TURNOS:]
    nuevo = HiloCFO(
        user_id=user_id,
        turnos=turnos,
        ultimo_update_id=update_id if set_dedup else (hilo.ultimo_update_id if hilo else None),
        ultimo_envio=mostrado if set_dedup else (hilo.ultimo_envio if hilo else None),
        actualizado_at=now_utc(),
    )
    await repositorio.guardar_hilo(nuevo)


async def registrar_turno(
    user_id: str, pregunta: str, texto_crudo: str, update_id: int, envio: str
) -> None:
    await _append_turnos(user_id, pregunta, texto_crudo, envio, "telegram",
                         update_id=update_id, set_dedup=True)


async def registrar_turno_web(
    user_id: str, pregunta: str, texto_crudo: str, mostrado: str
) -> None:
    await _append_turnos(user_id, pregunta, texto_crudo, mostrado, "web", set_dedup=False)


_LEGACY_ASSISTANT = "(respuesta anterior)"


def historial_para_display(hilo: HiloCFO | None) -> list[dict]:
    """Scrollback renderizado: user → su texto; assistant → `mostrado` (ya sustituido).
    Un assistant legacy sin `mostrado` se enmascara — NUNCA se expone el crudo con tokens."""
    if hilo is None or not hilo.turnos:
        return []
    out: list[dict] = []
    for t in hilo.turnos:
        rol = t.get("rol", "assistant")
        if rol == "user":
            texto = t.get("mostrado") or t.get("contenido") or ""
        else:
            texto = t.get("mostrado") or _LEGACY_ASSISTANT
        out.append({"rol": rol, "texto": texto,
                    "canal": t.get("canal", "desconocido"), "ts": t.get("ts")})
    return out
```

(La firma de `registrar_turno` NO cambia — el webhook la llama igual; ahora persiste `mostrado=envio` + `canal="telegram"`. `registrar_dedup`, `es_reintento`, `historial_para_loop` intactos.)

- [ ] **Step 4: Correr — verde** (hilos + los tests del webhook que sigan tocando `turnos`)

Run: `python -m pytest tests/cfo/telegram -q`
Expected: PASS. (Si algún test del webhook asserta la forma exacta de `turnos`, actualízalo a la nueva forma con `mostrado`/`canal`/`ts`.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/telegram/hilos.py backend/tests/cfo/telegram/
git commit -m "feat(cfo): log de display en el hilo (mostrado/canal/ts, retencion 200) + registrar_turno_web"
```

---

### Task 2: Backend — endpoint conversacional + historial

**Files:**
- Modify: `backend/app/cfo/router.py`
- Test: `backend/tests/cfo/test_router_chat.py` (nuevo)

**Interfaces:**
- Consumes: Task 1 (`registrar_turno_web`, `historial_para_display`), `hilos.historial_para_loop`, `repositorio.obtener_hilo`, `config.cfo_hilo_ventana`, `servicio.consultar`.
- Produces: `POST /api/v1/cfo` conversacional; `GET /api/v1/cfo/historial -> list[TurnoHistorial]`.

- [ ] **Step 1: Escribir el test** (fakea `servicio.consultar`; mock del RBAC)

```python
# backend/tests/cfo/test_router_chat.py
import pytest
import pytest_asyncio
from app.cfo import router as cfo_router
from app.cfo.agente.modelos import RespuestaCFO, CifraPublicada
from app.cfo.telegram import hilos, repositorio
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_consultar_es_conversacional_y_persiste(db, monkeypatch):
    monkeypatch.setattr(cfo_router, "cfo_enabled", lambda: True)
    capturado = {}

    async def fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        capturado["historial"] = historial
        capturado["actor_id"] = actor_id
        return RespuestaCFO(texto="$5.000 (al hoy)", abstuvo=False, texto_crudo="[[caja_hoy]]")

    monkeypatch.setattr(cfo_router.servicio, "consultar", fake_consultar)

    class _U: id = "u1"
    body = cfo_router.ConsultaBody(pregunta="cuánta caja?")
    resp = await cfo_router.consultar(body, user=_U())
    assert resp.texto == "$5.000 (al hoy)"
    assert capturado["actor_id"] == "u1"
    # persistió el turno con mostrado en el hilo del user
    hilo = await repositorio.obtener_hilo("u1")
    assert hilo.turnos[-1]["mostrado"] == "$5.000 (al hoy)"
    assert hilo.turnos[-1]["canal"] == "web"

    # segunda pregunta: ahora consultar recibe el historial del turno previo
    await cfo_router.consultar(cfo_router.ConsultaBody(pregunta="y ayer?"), user=_U())
    assert capturado["historial"]  # no vacío en el 2º turno


@pytest.mark.asyncio
async def test_historial_devuelve_scrollback(db, monkeypatch):
    monkeypatch.setattr(cfo_router, "cfo_enabled", lambda: True)
    await hilos.registrar_turno_web("u2", "hola", "[[x]]", "respuesta mostrada")

    class _U: id = "u2"
    out = await cfo_router.historial(user=_U())
    textos = [t["texto"] for t in out]
    assert "hola" in textos and "respuesta mostrada" in textos


@pytest.mark.asyncio
async def test_flag_off_da_404(db, monkeypatch):
    monkeypatch.setattr(cfo_router, "cfo_enabled", lambda: False)
    from fastapi import HTTPException

    class _U: id = "u3"
    with pytest.raises(HTTPException) as e:
        await cfo_router.consultar(cfo_router.ConsultaBody(pregunta="x"), user=_U())
    assert e.value.status_code == 404
```

- [ ] **Step 2: Correr — debe fallar**

Run: `python -m pytest tests/cfo/test_router_chat.py -q`
Expected: FAIL.

- [ ] **Step 3: Editar `router.py`**

```python
from app.cfo import config
from app.cfo.telegram import hilos, repositorio
# ... imports existentes ...


class TurnoHistorial(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    rol: str
    texto: str
    canal: str
    ts: str | None = None


@router.post("", response_model=RespuestaCFO)
async def consultar(
    body: ConsultaBody, user: User = Depends(require_permission("cfo:consultar"))
) -> RespuestaCFO:
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    uid = str(user.id)
    hilo = await repositorio.obtener_hilo(uid)
    historial = hilos.historial_para_loop(hilo, config.cfo_hilo_ventana())
    resp = await servicio.consultar(body.pregunta, actor_id=uid, historial=historial)
    await hilos.registrar_turno_web(uid, body.pregunta, resp.texto_crudo, resp.texto)
    return resp


@router.get("/historial", response_model=list[TurnoHistorial])
async def historial(
    user: User = Depends(require_permission("cfo:consultar")),
) -> list[dict]:
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    hilo = await repositorio.obtener_hilo(str(user.id))
    return hilos.historial_para_display(hilo)
```

- [ ] **Step 4: Correr — verde** (+ regresión cfo)

Run: `python -m pytest tests/cfo/test_router_chat.py tests/cfo -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/router.py backend/tests/cfo/test_router_chat.py
git commit -m "feat(cfo): POST /cfo conversacional sobre el hilo compartido + GET /cfo/historial"
```

---

### Task 3: Frontend — tipos + cliente de FABS

**Files:**
- Create: `frontend/src/lib/fabs.ts`
- Test: `frontend/src/lib/fabs.test.ts` (nuevo)

**Interfaces:**
- Produces: tipos `CifraFabs`, `RespuestaFabs`, `TurnoHistorial`; funciones `historialFabs()`, `preguntarFabs(pregunta)`.

- [ ] **Step 1: Escribir el test**

```ts
// frontend/src/lib/fabs.test.ts
import { describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { historialFabs, preguntarFabs } from "@/lib/fabs";

describe("fabs api", () => {
  it("preguntarFabs hace POST /cfo con JSON", async () => {
    const spy = vi.spyOn(api, "apiJson").mockResolvedValue({ texto: "ok", abstuvo: false, cifras: [] } as never);
    await preguntarFabs("hola");
    expect(spy).toHaveBeenCalledWith("/cfo", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ pregunta: "hola" }),
    }));
    spy.mockRestore();
  });

  it("historialFabs hace GET /cfo/historial", async () => {
    const spy = vi.spyOn(api, "apiJson").mockResolvedValue([] as never);
    await historialFabs();
    expect(spy).toHaveBeenCalledWith("/cfo/historial");
    spy.mockRestore();
  });
});
```

- [ ] **Step 2: Correr — debe fallar**

Run (desde `frontend/`): `npx vitest run src/lib/fabs.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implementar `fabs.ts`**

```ts
// frontend/src/lib/fabs.ts
// Cliente de FABS (chat embebido). Los montos llegan como string YA formateado
// es-CO dentro del texto — NUNCA hacer Number sobre ellos (regla 1).
import { apiJson } from "@/lib/api";

export interface CifraFabs {
  valor: string;
  unidad: string;
  evidencia: { fuente: string; ref: string };
}

export interface RespuestaFabs {
  texto: string;
  abstuvo: boolean;
  cifras: CifraFabs[];
}

export interface TurnoHistorial {
  rol: "user" | "assistant";
  texto: string;
  canal: string;
  ts: string | null;
}

export function historialFabs(): Promise<TurnoHistorial[]> {
  return apiJson<TurnoHistorial[]>("/cfo/historial");
}

export function preguntarFabs(pregunta: string): Promise<RespuestaFabs> {
  return apiJson<RespuestaFabs>("/cfo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta }),
  });
}
```

- [ ] **Step 4: Correr — verde**

Run: `npx vitest run src/lib/fabs.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/fabs.ts frontend/src/lib/fabs.test.ts
git commit -m "feat(frontend): cliente FABS (tipos + preguntarFabs/historialFabs)"
```

---

### Task 4: Frontend — panel acoplable + integración en el shell

**Files:**
- Create: `frontend/src/components/fabs/FabsPanel.tsx`
- Modify: `frontend/src/components/layout/AppShell.tsx` (botón + panel, gateado por `cfo:consultar`)
- Test: `frontend/src/components/fabs/FabsPanel.test.tsx` (nuevo)

**Interfaces:**
- Consumes: Task 3 (`preguntarFabs`, `historialFabs`, tipos), `useAuth().puede`.
- Produces: `FabsPanel` (slide-over funcional); botón "Preguntá a FABS" en el shell.

- [ ] **Step 1: Escribir el test**

```tsx
// frontend/src/components/fabs/FabsPanel.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as fabs from "@/lib/fabs";
import { FabsPanel } from "@/components/fabs/FabsPanel";

describe("FabsPanel", () => {
  it("carga el historial al montar y pinta las burbujas", async () => {
    vi.spyOn(fabs, "historialFabs").mockResolvedValue([
      { rol: "user", texto: "hola", canal: "telegram", ts: null },
      { rol: "assistant", texto: "$5.000.000 hoy", canal: "telegram", ts: null },
    ]);
    render(<FabsPanel onCerrar={() => {}} />);
    expect(await screen.findByText("hola")).toBeInTheDocument();
    expect(screen.getByText("$5.000.000 hoy")).toBeInTheDocument();
  });

  it("enviar pinta la pregunta y luego la respuesta con evidencia", async () => {
    vi.spyOn(fabs, "historialFabs").mockResolvedValue([]);
    vi.spyOn(fabs, "preguntarFabs").mockResolvedValue({
      texto: "La caja es $5.000.000",
      abstuvo: false,
      cifras: [{ valor: "5.000.000", unidad: "COP", evidencia: { fuente: "caja.py", ref: "2026-08" } }],
    });
    render(<FabsPanel onCerrar={() => {}} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "cuánta caja?" } });
    fireEvent.submit(screen.getByRole("textbox").closest("form")!);
    expect(await screen.findByText("cuánta caja?")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("La caja es $5.000.000")).toBeInTheDocument());
    expect(screen.getByText(/caja\.py/)).toBeInTheDocument();  // pie de evidencia
  });
});
```

> Nota de mocking: si `vi.spyOn(fabs, "…")` no intercepta el import nombrado en tu setup de Vitest, cambia a `vi.mock("@/lib/fabs", () => ({ historialFabs: vi.fn(), preguntarFabs: vi.fn() }))` y configura los retornos por test con `vi.mocked(...)`. Mantén las MISMAS aserciones de comportamiento.

- [ ] **Step 2: Correr — debe fallar**

Run: `npx vitest run src/components/fabs/FabsPanel.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implementar `FabsPanel.tsx`**

```tsx
// frontend/src/components/fabs/FabsPanel.tsx
// Panel acoplable de FABS (funcional; Cowork pule los visuales). Carga el scrollback
// cruzado al montar y agrega cada turno. Montos NUNCA con Number (regla 1) — se pintan
// tal cual (ya es-CO en el texto).
import { type FormEvent, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { historialFabs, preguntarFabs, type CifraFabs, type TurnoHistorial } from "@/lib/fabs";

interface Msg { rol: "user" | "assistant"; texto: string; canal?: string; cifras?: CifraFabs[] }

export function FabsPanel({ onCerrar }: { onCerrar: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    historialFabs()
      .then((h: TurnoHistorial[]) => setMsgs(h.map((t) => ({ rol: t.rol, texto: t.texto, canal: t.canal }))))
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudo cargar el historial."));
  }, []);

  useEffect(() => { finRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, cargando]);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    const pregunta = texto.trim();
    if (!pregunta || cargando) return;
    setError(null);
    setMsgs((m) => [...m, { rol: "user", texto: pregunta }]);
    setTexto("");
    setCargando(true);
    try {
      const r = await preguntarFabs(pregunta);
      setMsgs((m) => [...m, { rol: "assistant", texto: r.texto, cifras: r.cifras }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "FABS no está disponible.");
    } finally {
      setCargando(false);
    }
  }

  return (
    <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-surface shadow-xl">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-semibold">FABS</span>
        <button onClick={onCerrar} aria-label="Cerrar" className="text-muted-foreground">✕</button>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {msgs.length === 0 && !cargando && (
          <p className="text-sm text-muted-foreground">Preguntale algo a FABS sobre tu caja, presupuesto o proyección.</p>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.rol === "user" ? "text-right" : "text-left"}>
            <div className={`inline-block whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${m.rol === "user" ? "bg-primary/10" : "bg-surface-muted"}`}>
              {m.texto}
              {m.canal === "telegram" && <span className="ml-2 opacity-50" title="Desde Telegram">✈</span>}
              {m.cifras && m.cifras.length > 0 && (
                <ul className="mt-2 border-t border-border pt-1 text-xs text-muted-foreground">
                  {m.cifras.map((c, j) => (
                    <li key={j}>• {c.valor} {c.unidad} — {c.evidencia.fuente} ({c.evidencia.ref})</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}
        {cargando && <p className="text-sm text-muted-foreground">FABS está pensando…</p>}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div ref={finRef} />
      </div>
      <form onSubmit={enviar} className="border-t border-border p-3">
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Preguntá a FABS…"
          className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
      </form>
    </aside>
  );
}
```

- [ ] **Step 4: Integrar en `AppShell.tsx`**

Añadir estado + el botón (gateado por `puede("cfo:consultar")`) + el render del panel. Junto al `useAuth()` existente:

```tsx
import { useState } from "react";              // ya está
import { FabsPanel } from "@/components/fabs/FabsPanel";
// dentro de AppShell, junto a menuAbierto:
const [fabsAbierto, setFabsAbierto] = useState(false);
```

Renderizar, al final del árbol del shell (antes de cerrar el contenedor raíz), solo si hay permiso:

```tsx
{puede("cfo:consultar") && (
  <>
    <button
      onClick={() => setFabsAbierto(true)}
      className="fixed bottom-4 right-4 z-40 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-lg"
    >
      Preguntá a FABS
    </button>
    {fabsAbierto && <FabsPanel onCerrar={() => setFabsAbierto(false)} />}
  </>
)}
```

(`puede` ya se desestructura de `useAuth()` en AppShell.)

- [ ] **Step 5: Correr — verde + build**

Run (desde `frontend/`): `npx vitest run src/components/fabs/FabsPanel.test.tsx src/components/layout` y luego `npm run build`
Expected: PASS + build verde (tsc -b tipa los tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/fabs/ frontend/src/components/layout/AppShell.tsx
git commit -m "feat(frontend): panel acoplable de FABS + boton en el shell (gateado por cfo:consultar)"
```

---

### Task 5: Cierre — guardas + roadmap

**Files:**
- Modify: `docs/COMPAS_FABS_ROADMAP.md`

- [ ] **Step 1: Guardas**

Run:
```bash
git fetch origin -q
git diff --stat origin/main..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py && echo "motor 0 diffs OK"
cd backend && python -m pytest tests/cfo -q && python -m ruff check app/cfo && cd ..
cd frontend && npm run build && cd ..
```
Expected: motor 0 diffs; backend cfo verde; ruff limpio; build del front verde.

- [ ] **Step 2: Roadmap**

En `docs/COMPAS_FABS_ROADMAP.md` (léelo primero), añadir entrada fechada 2026-08-30 del chat embebido: inc5/6; `POST /cfo` conversacional sobre el hilo compartido + `GET /cfo/historial`; log de display (`mostrado`, retención 200); panel acoplable gateado por `cfo:consultar` (sin permiso nuevo); anti-alucinación intacta (scrollback = texto ya verificado); panel funcional aquí, Cowork pule; gate = gate-waiver + GO CEO (NO afirmar que Kimi aprobó).

- [ ] **Step 3: Commit**

```bash
git add docs/COMPAS_FABS_ROADMAP.md
git commit -m "docs(fabs): chat embebido — roadmap"
```

---

## Self-Review

**1. Spec coverage:** §5.1 endpoint conversacional→Task 2; §5.2 log de display→Task 1; §5.3 GET historial→Task 2; §5.4 panel→Tasks 3+4; §5.5 RBAC→Tasks 2 (backend) + 4 (front gating); §6 anti-alucinación→Task 1 (enmascara legacy) + Task 2 (mostrado verificado); §7 reglas→Global Constraints; §8 casos borde→Tasks 1/2/4; §9 testing→cada task; §10 fuera de alcance→respetado. Cubierto.

**2. Placeholder scan:** todo el código (backend + TS/TSX) es real; los tests traen aserciones concretas.

**3. Type consistency:** `registrar_turno_web(user_id, pregunta, texto_crudo, mostrado)` y `historial_para_display(hilo)->list[dict]` (Tasks 1/2). `TurnoHistorial {rol, texto, canal, ts}` (backend Task 2) ↔ `TurnoHistorial {rol, texto, canal, ts}` (front Task 3) coinciden. `RespuestaFabs {texto, abstuvo, cifras}` ↔ `RespuestaCFO`. `CifraFabs {valor, unidad, evidencia:{fuente,ref}}` ↔ `CifraPublicada`. `preguntarFabs/historialFabs` (Task 3) consumidos por `FabsPanel` (Task 4). `puede("cfo:consultar")` gating. Consistente.
