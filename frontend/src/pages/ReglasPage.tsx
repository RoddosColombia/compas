// frontend/src/pages/ReglasPage.tsx
//
// C3 auto-clasificación (CR-S5): administrar las reglas que clasifican los
// movimientos al cargar. Tabla por tipo de flujo (prioridad ascendente = orden
// real de evaluación), crear, editar (patrón/prioridad/rubro destino),
// desactivar/reactivar, aprobar propuestas APRENDIDAS (§1.9: nunca
// auto-activadas), y "Aplicar a pendientes" con su reporte (clasificadas /
// sin match / reglas con rubro inactivo — simetría D2). Botones solo con
// reglas:gestionar (regla 9); la autoridad real la impone el backend.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import {
  type Regla,
  type ResultadoAplicar,
  aplicarPendientes,
  aprobarRegla,
  crearRegla,
  desactivarRegla,
  editarRegla,
  listarReglas,
  reactivarRegla,
} from "@/lib/reglas";
import { type Rubro, type TipoFlujo, listarRubros } from "@/lib/rubros";

export default function ReglasPage() {
  const { puede } = useAuth();
  const gestiona = puede("reglas:gestionar");
  const qc = useQueryClient();
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [reporte, setReporte] = useState<ResultadoAplicar | null>(null);

  const reglas = useQuery({ queryKey: ["reglas"], queryFn: listarReglas });
  const rubros = useQuery({ queryKey: ["rubros"], queryFn: listarRubros });

  const alTerminar = {
    onSuccess: () => {
      setMensaje(null);
      qc.invalidateQueries({ queryKey: ["reglas"] });
    },
    onError: (e: unknown) =>
      setMensaje(e instanceof Error ? e.message : "Error"),
  };
  const crear = useMutation({ mutationFn: crearRegla, ...alTerminar });
  const editar = useMutation({ mutationFn: editarRegla, ...alTerminar });
  const desactivar = useMutation({
    mutationFn: desactivarRegla,
    ...alTerminar,
  });
  const reactivar = useMutation({ mutationFn: reactivarRegla, ...alTerminar });
  const aprobar = useMutation({ mutationFn: aprobarRegla, ...alTerminar });
  const aplicar = useMutation({
    mutationFn: aplicarPendientes,
    onSuccess: (r) => {
      setMensaje(null);
      setReporte(r);
    },
    onError: (e: unknown) =>
      setMensaje(e instanceof Error ? e.message : "Error"),
  });

  const rubroPorId = new Map((rubros.data ?? []).map((r) => [r.id, r]));
  const egresos = (reglas.data ?? []).filter((r) => r.tipo_flujo === "egreso");
  const ingresos = (reglas.data ?? []).filter(
    (r) => r.tipo_flujo === "ingreso",
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Reglas"
        descripcion="Primera regla que coincide (por prioridad) clasifica el movimiento; sin coincidencia → «Por clasificar»."
        acciones={
          gestiona ? (
            <Button
              size="sm"
              variant="outline"
              disabled={aplicar.isPending}
              onClick={() => aplicar.mutate()}
            >
              {aplicar.isPending ? "Aplicando…" : "Aplicar a pendientes"}
            </Button>
          ) : undefined
        }
      />

      {mensaje && <AlertBanner variant="danger">{mensaje}</AlertBanner>}

      {reporte && (
        <Card className="font-sans text-sm text-ink-soft">
          <span className="font-semibold text-cyan">Aplicado:</span>{" "}
          {reporte.clasificadas} clasificadas · {reporte.sin_match} sin
          coincidencia
          {reporte.reglas_con_rubro_inactivo.length > 0 && (
            <>
              {" "}
              ·{" "}
              <span className="font-semibold text-atencion">
                reglas con categoría inactiva:
              </span>{" "}
              {reporte.reglas_con_rubro_inactivo.join(" · ")}
            </>
          )}
        </Card>
      )}

      {(reglas.isLoading || rubros.isLoading) && (
        <p className="font-sans text-sm text-ink-soft">Cargando reglas…</p>
      )}
      {reglas.isError && (
        <AlertBanner variant="danger">
          No se pudieron cargar las reglas.
        </AlertBanner>
      )}

      {reglas.data && rubros.data && (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full font-sans text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-ink-faint">
                  <th className="px-4 py-2.5 font-semibold">
                    Patrón (contiene)
                  </th>
                  <th className="px-4 py-2.5 font-semibold">
                    Categoría destino
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Prioridad
                  </th>
                  <th className="px-4 py-2.5 font-semibold">Origen</th>
                  <th className="px-4 py-2.5 font-semibold">Estado</th>
                  {gestiona && <th className="px-4 py-2.5 font-semibold" />}
                </tr>
              </thead>
              <tbody>
                <BloqueTipo
                  titulo="Egresos"
                  filas={egresos}
                  rubroPorId={rubroPorId}
                  rubros={rubros.data}
                  gestiona={gestiona}
                  onEditar={(i) => editar.mutate(i)}
                  onDesactivar={(id) => desactivar.mutate(id)}
                  onReactivar={(id) => reactivar.mutate(id)}
                  onAprobar={(id) => aprobar.mutate(id)}
                />
                <BloqueTipo
                  titulo="Ingresos"
                  filas={ingresos}
                  rubroPorId={rubroPorId}
                  rubros={rubros.data}
                  gestiona={gestiona}
                  onEditar={(i) => editar.mutate(i)}
                  onDesactivar={(id) => desactivar.mutate(id)}
                  onReactivar={(id) => reactivar.mutate(id)}
                  onAprobar={(id) => aprobar.mutate(id)}
                />
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {gestiona && rubros.data && (
        <FormNueva
          rubros={rubros.data}
          creando={crear.isPending}
          onCrear={(i) => crear.mutate(i)}
        />
      )}
    </div>
  );
}

interface AccionesProps {
  gestiona: boolean;
  rubros: Rubro[];
  rubroPorId: Map<string, Rubro>;
  onEditar: (input: {
    id: string;
    patron?: string;
    prioridad?: number;
    rubro_id?: string;
  }) => void;
  onDesactivar: (id: string) => void;
  onReactivar: (id: string) => void;
  onAprobar: (id: string) => void;
}

function BloqueTipo({
  titulo,
  filas,
  ...resto
}: { titulo: string; filas: Regla[] } & AccionesProps) {
  if (filas.length === 0) return null;
  const cols = resto.gestiona ? 6 : 5;
  return (
    <>
      <tr className="bg-surface-muted">
        <td
          colSpan={cols}
          className="px-4 py-1.5 font-sans text-apoyo font-semibold tracking-wide text-ink-faint uppercase"
        >
          {titulo}
        </td>
      </tr>
      {filas.map((r) => (
        <FilaRegla key={r.id} regla={r} {...resto} />
      ))}
    </>
  );
}

function FilaRegla({
  regla,
  gestiona,
  rubros,
  rubroPorId,
  onEditar,
  onDesactivar,
  onReactivar,
  onAprobar,
}: { regla: Regla } & AccionesProps) {
  const [editando, setEditando] = useState(false);
  const [patron, setPatron] = useState(regla.patron);
  const [prioridad, setPrioridad] = useState(String(regla.prioridad));
  const [rubroId, setRubroId] = useState(regla.rubro_id);

  const rubro = rubroPorId.get(regla.rubro_id);
  const rubroInactivo = rubro !== undefined && !rubro.activo;
  const propuesta = regla.origen === "aprendida" && !regla.activa;
  const destinos = rubros.filter(
    (r) => r.tipo_flujo === regla.tipo_flujo && r.activo,
  );

  function guardar() {
    const cambios: {
      id: string;
      patron?: string;
      prioridad?: number;
      rubro_id?: string;
    } = { id: regla.id };
    if (patron.trim().length >= 3 && patron.trim() !== regla.patron)
      cambios.patron = patron.trim();
    const p = Number.parseInt(prioridad, 10);
    if (Number.isInteger(p) && p !== regla.prioridad) cambios.prioridad = p;
    if (rubroId !== regla.rubro_id) cambios.rubro_id = rubroId;
    if (Object.keys(cambios).length > 1) onEditar(cambios);
    setEditando(false);
  }

  const inputCls =
    "rounded-md border border-hairline bg-surface px-2 py-1 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan";

  if (editando) {
    return (
      <tr className="border-b border-hairline/60 bg-cyan-tint">
        <td className="px-4 py-2">
          <input
            className={`w-full ${inputCls}`}
            value={patron}
            maxLength={120}
            aria-label={`Patrón de ${regla.patron}`}
            onChange={(e) => setPatron(e.target.value)}
          />
        </td>
        <td className="px-4 py-2">
          <select
            className={inputCls}
            value={rubroId}
            aria-label={`Destino de ${regla.patron}`}
            onChange={(e) => setRubroId(e.target.value)}
          >
            {destinos.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nombre}
              </option>
            ))}
          </select>
        </td>
        <td className="px-4 py-2 text-right">
          <input
            className={`w-16 text-right ${inputCls}`}
            value={prioridad}
            inputMode="numeric"
            aria-label={`Prioridad de ${regla.patron}`}
            onChange={(e) => setPrioridad(e.target.value)}
          />
        </td>
        <td className="px-4 py-2 text-apoyo text-ink-soft">{regla.origen}</td>
        <td className="px-4 py-2">
          <EstadoBadge regla={regla} rubroInactivo={rubroInactivo} />
        </td>
        <td className="flex gap-2 px-4 py-2">
          <Button size="sm" variant="cyan" onClick={guardar}>
            Guardar
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setPatron(regla.patron);
              setPrioridad(String(regla.prioridad));
              setRubroId(regla.rubro_id);
              setEditando(false);
            }}
          >
            Cancelar
          </Button>
        </td>
      </tr>
    );
  }

  return (
    <tr
      className={`border-b border-hairline/60 ${regla.activa ? "" : "text-ink-faint"}`}
    >
      <td className="tabular px-4 py-2 text-apoyo text-ink">{regla.patron}</td>
      <td className="px-4 py-2 text-ink">
        {rubro?.nombre ?? regla.rubro_id}
        {rubroInactivo && (
          <span
            className="ml-2 rounded-full bg-atencion/10 px-2 py-0.5 text-apoyo font-medium text-atencion"
            title="La regla se salta al clasificar (D2): su categoría está inactiva"
          >
            categoría inactiva
          </span>
        )}
      </td>
      <td className="tabular px-4 py-2 text-right text-ink-soft">
        {regla.prioridad}
      </td>
      <td className="px-4 py-2 text-apoyo text-ink-soft">{regla.origen}</td>
      <td className="px-4 py-2">
        <EstadoBadge regla={regla} rubroInactivo={rubroInactivo} />
      </td>
      {gestiona && (
        <td className="flex gap-2 px-4 py-2">
          {propuesta && (
            <Button
              size="sm"
              variant="cyan"
              onClick={() => onAprobar(regla.id)}
            >
              Aprobar
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => setEditando(true)}>
            Editar
          </Button>
          {regla.activa ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onDesactivar(regla.id)}
            >
              Desactivar
            </Button>
          ) : (
            !propuesta && (
              <Button
                size="sm"
                variant="cyan"
                onClick={() => onReactivar(regla.id)}
              >
                Reactivar
              </Button>
            )
          )}
        </td>
      )}
    </tr>
  );
}

function EstadoBadge({
  regla,
  rubroInactivo,
}: {
  regla: Regla;
  rubroInactivo: boolean;
}) {
  if (regla.origen === "aprendida" && !regla.activa) {
    return (
      <span className="rounded-full bg-atencion/10 px-2 py-0.5 text-apoyo font-medium text-atencion">
        Propuesta
      </span>
    );
  }
  if (!regla.activa) {
    return (
      <span className="rounded-full bg-surface-muted px-2 py-0.5 text-apoyo font-medium text-ink-faint">
        Inactiva
      </span>
    );
  }
  if (rubroInactivo) {
    return (
      <span className="rounded-full bg-atencion/10 px-2 py-0.5 text-apoyo font-medium text-atencion">
        Sin efecto
      </span>
    );
  }
  return (
    <span className="rounded-full bg-positivo/10 px-2 py-0.5 text-apoyo font-medium text-positivo">
      Activa
    </span>
  );
}

function FormNueva({
  rubros,
  creando,
  onCrear,
}: {
  rubros: Rubro[];
  creando: boolean;
  onCrear: (input: {
    patron: string;
    rubro_id: string;
    tipo_flujo: TipoFlujo;
    prioridad: number;
  }) => void;
}) {
  const [tipo, setTipo] = useState<TipoFlujo>("egreso");
  const [patron, setPatron] = useState("");
  const [rubroId, setRubroId] = useState("");
  const [prioridad, setPrioridad] = useState("100");

  const destinos = rubros.filter((r) => r.tipo_flujo === tipo && r.activo);
  const valido =
    patron.trim().length >= 3 &&
    rubroId !== "" &&
    Number.isInteger(Number.parseInt(prioridad, 10));

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (!valido) return;
    onCrear({
      patron: patron.trim(),
      rubro_id: rubroId,
      tipo_flujo: tipo,
      prioridad: Number.parseInt(prioridad, 10),
    });
    setPatron("");
  }

  const inputCls =
    "rounded-md border border-hairline bg-surface px-2 py-1.5 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan";

  return (
    <Card>
      <CardTitle>Nueva regla</CardTitle>
      <form onSubmit={enviar} className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Tipo
          <select
            className={inputCls}
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value as TipoFlujo);
              setRubroId("");
            }}
          >
            <option value="egreso">Egreso</option>
            <option value="ingreso">Ingreso</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Si la descripción contiene…
          <input
            className={`w-64 ${inputCls}`}
            value={patron}
            minLength={3}
            maxLength={120}
            placeholder="mín. 3 caracteres"
            onChange={(e) => setPatron(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Clasificar en
          <select
            className={inputCls}
            value={rubroId}
            onChange={(e) => setRubroId(e.target.value)}
          >
            <option value="">— categoría —</option>
            {destinos.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Prioridad
          <input
            className={`w-20 text-right ${inputCls}`}
            value={prioridad}
            inputMode="numeric"
            onChange={(e) => setPrioridad(e.target.value)}
          />
        </label>
        <Button
          type="submit"
          variant="cyan"
          size="sm"
          disabled={creando || !valido}
        >
          {creando ? "Creando…" : "Crear"}
        </Button>
      </form>
    </Card>
  );
}
