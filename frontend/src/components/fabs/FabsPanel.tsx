// Panel acoplable de FABS (funcional; Cowork pule los visuales). Carga el scrollback
// cruzado al montar y agrega cada turno. Montos NUNCA con Number (regla 1) — se pintan
// tal cual (ya es-CO en el texto).
import { type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { historialFabs, preguntarFabs, type CifraFabs, type TurnoHistorial } from "@/lib/fabs";

interface Msg {
  rol: "user" | "assistant";
  texto: string;
  canal?: string;
  cifras?: CifraFabs[];
}

export function FabsPanel({ onCerrar }: { onCerrar: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    historialFabs()
      .then((h: TurnoHistorial[]) =>
        setMsgs(h.map((t) => ({ rol: t.rol, texto: t.texto, canal: t.canal }))),
      )
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudo cargar el historial."));
  }, []);

  useEffect(() => {
    finRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [msgs, cargando]);

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
    <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-hairline bg-surface shadow-xl">
      <header className="flex items-center justify-between border-b border-hairline px-4 py-3">
        <span className="font-display font-semibold text-ink">FABS</span>
        <button
          type="button"
          onClick={onCerrar}
          aria-label="Cerrar"
          className="text-ink-faint hover:text-ink"
        >
          ✕
        </button>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {msgs.length === 0 && !cargando && (
          <p className="font-sans text-cuerpo text-ink-faint">
            Preguntale algo a FABS sobre tu caja, presupuesto o proyección.
          </p>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.rol === "user" ? "text-right" : "text-left"}>
            <div
              className={`inline-block max-w-full whitespace-pre-wrap rounded-lg px-3 py-2 text-left font-sans text-cuerpo ${
                m.rol === "user" ? "bg-cyan-tint text-ink" : "bg-surface-muted text-ink"
              }`}
            >
              {m.texto}
              {m.canal === "telegram" && (
                <span className="ml-2 text-ink-faint" title="Desde Telegram">
                  ✈
                </span>
              )}
              {m.cifras && m.cifras.length > 0 && (
                <ul className="mt-2 border-t border-hairline pt-1 text-apoyo text-ink-faint">
                  {m.cifras.map((c, j) => (
                    <li key={j}>
                      • {c.valor} {c.unidad} — {c.evidencia.fuente} ({c.evidencia.ref})
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}
        {cargando && <p className="font-sans text-cuerpo text-ink-faint">FABS está pensando…</p>}
        {error && <p className="font-sans text-cuerpo text-critico">{error}</p>}
        <div ref={finRef} />
      </div>
      <form onSubmit={enviar} className="border-t border-hairline p-3">
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Preguntá a FABS…"
          className="w-full rounded-md border border-hairline bg-surface px-3 py-2 font-sans text-cuerpo text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
        />
      </form>
    </aside>
  );
}
