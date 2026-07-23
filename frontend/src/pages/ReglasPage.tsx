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
import { Button } from "@/components/ui/button";
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
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Reglas de clasificación</h2>
          <p className="text-xs text-slate-400">
            Primera regla que coincide (por prioridad) clasifica el movimiento;
            sin coincidencia → «Por clasificar»
          </p>
        </div>
        {gestiona && (
          <Button
            size="sm"
            variant="outline"
            disabled={aplicar.isPending}
            onClick={() => aplicar.mutate()}
          >
            {aplicar.isPending ? "Aplicando…" : "Aplicar a pendientes"}
          </Button>
        )}
      </header>

      {mensaje && (
        <p className="rounded-md bg-alert/10 px-3 py-2 text-sm text-alert">
          {mensaje}
        </p>
      )}

      {reporte && (
        <div className="rounded-md bg-turq/10 px-3 py-2 text-sm text-slate-700">
          <span className="font-medium text-turq">Aplicado:</span>{" "}
          {reporte.clasificadas} clasificadas · {reporte.sin_match} sin
          coincidencia
          {reporte.reglas_con_rubro_inactivo.length > 0 && (
            <>
              {" "}
              ·{" "}
              <span className="font-medium text-warn">
                reglas con categoría inactiva:
              </span>{" "}
              {reporte.reglas_con_rubro_inactivo.join(" · ")}
            </>
          )}
        </div>
      )}

      {(reglas.isLoading || rubros.isLoading) && (
        <p className="text-sm text-slate-500">Cargando reglas…</p>
      )}
      {reglas.isError && (
        <p className="text-sm text-alert">No se pudieron cargar las reglas.</p>
      )}

      {reglas.data && rubros.data && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-4">Patrón (contiene)</th>
                <th className="py-2 pr-4">Categoría destino</th>
                <th className="py-2 pr-4 text-right">Prioridad</th>
                <th className="py-2 pr-4">Origen</th>
                <th className="py-2 pr-4">Estado</th>
                {gestiona && <th className="py-2 pr-4">Acciones</th>}
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
      <tr className="bg-slate-50">
        <td
          colSpan={cols}
          className="py-1.5 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500"
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

  if (editando) {
    return (
      <tr className="border-b border-slate-100 bg-turq/5">
        <td className="py-2 pr-4">
          <input
            className="w-full rounded-md border border-slate-300 px-2 py-1"
            value={patron}
            maxLength={120}
            aria-label={`Patrón de ${regla.patron}`}
            onChange={(e) => setPatron(e.target.value)}
          />
        </td>
        <td className="py-2 pr-4">
          <select
            className="rounded-md border border-slate-300 px-2 py-1"
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
        <td className="py-2 pr-4 text-right">
          <input
            className="w-16 rounded-md border border-slate-300 px-2 py-1 text-right"
            value={prioridad}
            inputMode="numeric"
            aria-label={`Prioridad de ${regla.patron}`}
            onChange={(e) => setPrioridad(e.target.value)}
          />
        </td>
        <td className="py-2 pr-4 text-xs text-slate-500">{regla.origen}</td>
        <td className="py-2 pr-4">
          <EstadoBadge regla={regla} rubroInactivo={rubroInactivo} />
        </td>
        <td className="flex gap-2 py-2 pr-4">
          <Button size="sm" onClick={guardar}>
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
      className={`border-b border-slate-100 ${regla.activa ? "" : "text-slate-400"}`}
    >
      <td className="py-2 pr-4 font-mono text-xs">{regla.patron}</td>
      <td className="py-2 pr-4">
        {rubro?.nombre ?? regla.rubro_id}
        {rubroInactivo && (
          <span
            className="ml-2 rounded-full bg-warn/20 px-2 py-0.5 text-xs font-medium text-warn"
            title="La regla se salta al clasificar (D2): su categoría está inactiva"
          >
            categoría inactiva
          </span>
        )}
      </td>
      <td className="py-2 pr-4 text-right font-mono">{regla.prioridad}</td>
      <td className="py-2 pr-4 text-xs text-slate-500">{regla.origen}</td>
      <td className="py-2 pr-4">
        <EstadoBadge regla={regla} rubroInactivo={rubroInactivo} />
      </td>
      {gestiona && (
        <td className="flex gap-2 py-2 pr-4">
          {propuesta && (
            <Button size="sm" onClick={() => onAprobar(regla.id)}>
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
              <Button size="sm" onClick={() => onReactivar(regla.id)}>
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
      <span className="rounded-full bg-warn/20 px-2 py-0.5 text-xs font-medium text-warn">
        Propuesta
      </span>
    );
  }
  if (!regla.activa) {
    return (
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
        Inactiva
      </span>
    );
  }
  if (rubroInactivo) {
    return (
      <span className="rounded-full bg-warn/20 px-2 py-0.5 text-xs font-medium text-warn">
        Sin efecto
      </span>
    );
  }
  return (
    <span className="rounded-full bg-brand-soft/20 px-2 py-0.5 text-xs font-medium text-brand">
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

  return (
    <form
      onSubmit={enviar}
      className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 p-4"
    >
      <p className="w-full text-sm font-medium">Nueva regla</p>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Tipo
        <select
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
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
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Si la descripción contiene…
        <input
          className="w-64 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
          value={patron}
          minLength={3}
          maxLength={120}
          placeholder="mín. 3 caracteres"
          onChange={(e) => setPatron(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Clasificar en
        <select
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
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
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Prioridad
        <input
          className="w-20 rounded-md border border-slate-300 px-2 py-1.5 text-right text-sm text-slate-800"
          value={prioridad}
          inputMode="numeric"
          onChange={(e) => setPrioridad(e.target.value)}
        />
      </label>
      <Button type="submit" size="sm" disabled={creando || !valido}>
        {creando ? "Creando…" : "Crear"}
      </Button>
    </form>
  );
}
