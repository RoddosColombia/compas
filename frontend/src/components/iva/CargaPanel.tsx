// Panel de carga de facturas (spec de diseño §4). Dentro de /iva, no ítem del sidebar.
// Arrastrar y soltar Y botón. Sube los PDF de a uno (para la barra "n de N" real; el
// backend deduplica por CUFE contra la base, así que secuencial es correcto) y agrupa
// el resultado con los TEXTOS EXACTOS del §4 — sin jerga de estados del API.

import { type DragEvent, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import {
  type CargaResultado,
  type EstadoCarga,
  cargarFacturas,
  cargarFacturasExcel,
} from "@/lib/facturas";

const MAX = 20;

// Motivo en español por estado (§4). No se muestra el nombre del estado del API.
const MOTIVO: Record<EstadoCarga, string> = {
  creada: "",
  duplicada: "Ya estaba cargada (mismo CUFE).",
  rechazada_no_dian:
    "No parece la representación gráfica de la DIAN. Descarga el PDF desde el portal de la DIAN.",
  rechazada_tipo_no_soportado:
    "Es una nota crédito. Todavía no las procesamos; no entró a la liquidación.",
  requiere_confirmacion:
    "Los totales del documento no cuadran: necesita que la revises.",
  error: "No se pudo procesar el archivo.",
};

function plural(n: number, uno: string, varios: string): string {
  return `${n} ${n === 1 ? uno : varios}`;
}

interface Grupo {
  clave: string;
  titulo: string;
  tono: string;
  items: CargaResultado[];
}

function agrupar(resultados: CargaResultado[]): Grupo[] {
  const creadas = resultados.filter((r) => r.estado === "creada");
  const duplicadas = resultados.filter((r) => r.estado === "duplicada");
  const revisar = resultados.filter(
    (r) => r.estado === "requiere_confirmacion",
  );
  const fallidas = resultados.filter((r) =>
    ["rechazada_no_dian", "rechazada_tipo_no_soportado", "error"].includes(
      r.estado,
    ),
  );
  return [
    {
      clave: "creadas",
      titulo: plural(creadas.length, "factura cargada", "facturas cargadas"),
      tono: "text-positivo",
      items: creadas,
    },
    {
      clave: "duplicadas",
      titulo: plural(
        duplicadas.length,
        "ya estaba cargada",
        "ya estaban cargadas",
      ),
      tono: "text-ink-faint",
      items: duplicadas,
    },
    {
      clave: "revisar",
      titulo: plural(
        revisar.length,
        "necesita que la revises",
        "necesitan que las revises",
      ),
      tono: "text-atencion",
      items: revisar,
    },
    {
      clave: "fallidas",
      titulo: plural(
        fallidas.length,
        "no se pudo procesar",
        "no se pudieron procesar",
      ),
      tono: "text-atencion",
      items: fallidas,
    },
  ];
}

export function CargaPanel({
  onCerrar,
  onCargado,
  onRevisar,
}: {
  onCerrar: () => void;
  /** Tras la carga: refresca liquidación Y tabla (§2). */
  onCargado: () => void;
  /** Abre la pantalla de confirmación para un documento (requiere_confirmacion). */
  onRevisar?: (r: CargaResultado) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [arrastrando, setArrastrando] = useState(false);
  const [progreso, setProgreso] = useState<{
    n: number;
    total: number;
    archivo: string;
  } | null>(null);
  const [resultados, setResultados] = useState<CargaResultado[] | null>(null);

  async function subir(files: File[]) {
    const lote = files.slice(0, MAX);
    const acc: CargaResultado[] = [];
    for (let i = 0; i < lote.length; i++) {
      setProgreso({ n: i + 1, total: lote.length, archivo: lote[i].name });
      const esExcel = lote[i].name.toLowerCase().endsWith(".xlsx");
      try {
        // C2': un Excel de la DIAN trae CIENTOS de filas en un solo archivo —
        // va al endpoint masivo; los PDF siguen de a uno (barra n de N real).
        const resp = esExcel
          ? await cargarFacturasExcel(lote[i])
          : await cargarFacturas([lote[i]]);
        acc.push(...resp.resultados);
      } catch (e) {
        acc.push({
          archivo: lote[i].name,
          estado: "error",
          motivo: e instanceof Error ? e.message : null,
          factura_id: null,
          datos_extraidos: null,
        });
      }
    }
    setProgreso(null);
    setResultados(acc);
    onCargado(); // §2: recalcula titular + desglose + "qué exige atención" + tabla
  }

  function alSoltar(e: DragEvent) {
    e.preventDefault();
    setArrastrando(false);
    const files = Array.from(e.dataTransfer.files).filter(
      (f) =>
        f.name.toLowerCase().endsWith(".pdf") ||
        f.name.toLowerCase().endsWith(".xlsx"),
    );
    if (files.length) void subir(files);
  }

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <CardTitle>Cargar facturas</CardTitle>
        <Button type="button" variant="ghost" size="sm" onClick={onCerrar}>
          Cerrar
        </Button>
      </div>

      {!resultados && !progreso && (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setArrastrando(true);
          }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={alSoltar}
          className={`flex flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
            arrastrando
              ? "border-cyan bg-cyan-tint"
              : "border-hairline hover:bg-surface-muted"
          }`}
        >
          <span className="font-sans text-cuerpo text-ink">
            Arrastra aquí los PDF que descargas de la DIAN — hasta 20 archivos
          </span>
          <span className="font-sans text-apoyo text-ink-faint">
            o el Excel de «documentos recibidos» del portal (carga masiva) · o
            haz clic para seleccionar
          </span>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.xlsx"
            multiple
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              if (files.length) void subir(files);
            }}
          />
        </button>
      )}

      {progreso && (
        <div className="flex flex-col gap-2" aria-label="Cargando facturas">
          <div className="flex justify-between font-sans text-apoyo text-ink-soft">
            <span>
              {progreso.n} de {progreso.total}
            </span>
            <span className="truncate">{progreso.archivo}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full rounded-full bg-cyan transition-all"
              style={{ width: `${(progreso.n / progreso.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {resultados && (
        <div className="flex flex-col gap-3">
          {agrupar(resultados).map((g) => (
            <div key={g.clave}>
              <p className={`font-sans text-cuerpo font-semibold ${g.tono}`}>
                {g.titulo}
              </p>
              {g.clave !== "creadas" &&
                g.items.map((r, i) => (
                  <p
                    key={`${r.archivo}-${i}`}
                    className="pl-4 font-sans text-apoyo text-ink-faint"
                  >
                    {r.archivo}
                    {r.estado === "requiere_confirmacion" ? (
                      <>
                        {" — "}
                        <button
                          type="button"
                          onClick={() => onRevisar?.(r)}
                          className="font-medium text-cyan hover:underline"
                        >
                          Revisar
                        </button>
                      </>
                    ) : (
                      (r.motivo || MOTIVO[r.estado]) &&
                      ` — ${r.motivo || MOTIVO[r.estado]}`
                    )}
                  </p>
                ))}
            </div>
          ))}
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setResultados(null)}
            >
              Cargar más
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={onCerrar}>
              Listo
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
