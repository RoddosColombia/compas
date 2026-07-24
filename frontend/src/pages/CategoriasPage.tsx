// frontend/src/pages/CategoriasPage.tsx
//
// C1 categorías administrables (CR-S4) + plan de cuentas (ARQUITECTURA_PRESUPUESTAL):
// listar por grupo con Código y Clase (Fijo/Variable), crear, editar
// (nombre/orden/naturaleza/código/clase), desactivar (baja lógica) y reactivar. Los
// botones de mutación solo aparecen con rubros:gestionar (regla 9); la autoridad
// real la impone el backend. Los rubros de sistema son inmutables. Las guardas de
// dominio (tipo_flujo congelado B-1, duplicados, sistema) viven en el backend.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import { GRUPO_LABEL } from "@/lib/control";
import {
  type Rubro,
  type TipoFlujo,
  type TipoRubro,
  agruparRubros,
  crearRubro,
  desactivarRubro,
  editarRubro,
  listarRubros,
  reactivarRubro,
} from "@/lib/rubros";

interface EditarInput {
  id: string;
  nombre?: string;
  orden?: number;
  tipo_flujo?: TipoFlujo;
  codigo?: string;
  tipo?: TipoRubro;
}

export default function CategoriasPage() {
  const { puede } = useAuth();
  const gestiona = puede("rubros:gestionar");
  const qc = useQueryClient();
  const [mensaje, setMensaje] = useState<string | null>(null);

  const rubros = useQuery({ queryKey: ["rubros"], queryFn: listarRubros });

  const alTerminar = {
    onSuccess: () => {
      setMensaje(null);
      qc.invalidateQueries({ queryKey: ["rubros"] });
    },
    onError: (e: unknown) =>
      setMensaje(e instanceof Error ? e.message : "Error"),
  };
  const crear = useMutation({ mutationFn: crearRubro, ...alTerminar });
  const editar = useMutation({ mutationFn: editarRubro, ...alTerminar });
  const desactivar = useMutation({
    mutationFn: desactivarRubro,
    ...alTerminar,
  });
  const reactivar = useMutation({ mutationFn: reactivarRubro, ...alTerminar });

  const grupos = rubros.data ? agruparRubros(rubros.data) : null;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Categorías</h2>
        <p className="text-xs text-slate-400">
          El plan de cuentas del presupuesto — código, grupo y clase
          (fijo/variable)
        </p>
      </header>

      {mensaje && (
        <p className="rounded-md bg-alert/10 px-3 py-2 text-sm text-alert">
          {mensaje}
        </p>
      )}

      {rubros.isLoading && (
        <p className="text-sm text-slate-500">Cargando categorías…</p>
      )}
      {rubros.isError && (
        <p className="text-sm text-alert">
          No se pudieron cargar las categorías.
        </p>
      )}

      {grupos && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-4">Código</th>
                <th className="py-2 pr-4">Categoría</th>
                <th className="py-2 pr-4">Naturaleza</th>
                <th className="py-2 pr-4">Clase</th>
                <th className="py-2 pr-4 text-right">Orden</th>
                <th className="py-2 pr-4">Estado</th>
                {gestiona && <th className="py-2 pr-4">Acciones</th>}
              </tr>
            </thead>
            <tbody>
              {[...grupos.entries()].map(([grupo, filas]) => (
                <GrupoBloque
                  key={grupo}
                  grupo={grupo}
                  filas={filas}
                  gestiona={gestiona}
                  onEditar={(input) => editar.mutate(input)}
                  onDesactivar={(id) => desactivar.mutate(id)}
                  onReactivar={(id) => reactivar.mutate(id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {gestiona && (
        <FormNueva
          creando={crear.isPending}
          onCrear={(input) => crear.mutate(input)}
        />
      )}
    </div>
  );
}

function GrupoBloque({
  grupo,
  filas,
  gestiona,
  onEditar,
  onDesactivar,
  onReactivar,
}: {
  grupo: string;
  filas: Rubro[];
  gestiona: boolean;
  onEditar: (input: EditarInput) => void;
  onDesactivar: (id: string) => void;
  onReactivar: (id: string) => void;
}) {
  const cols = gestiona ? 7 : 6;
  return (
    <>
      <tr className="bg-slate-50">
        <td
          colSpan={cols}
          className="py-1.5 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500"
        >
          {GRUPO_LABEL[grupo] ?? grupo}
        </td>
      </tr>
      {filas.map((r) => (
        <FilaRubro
          key={r.id}
          rubro={r}
          gestiona={gestiona}
          onEditar={onEditar}
          onDesactivar={onDesactivar}
          onReactivar={onReactivar}
        />
      ))}
    </>
  );
}

function ClaseBadge({ tipo }: { tipo: TipoRubro | null }) {
  if (tipo === null) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        tipo === "fijo" ? "bg-slate-200 text-slate-700" : "bg-turq/15 text-turq"
      }`}
    >
      {tipo === "fijo" ? "Fijo" : "Variable"}
    </span>
  );
}

function FilaRubro({
  rubro,
  gestiona,
  onEditar,
  onDesactivar,
  onReactivar,
}: {
  rubro: Rubro;
  gestiona: boolean;
  onEditar: (input: EditarInput) => void;
  onDesactivar: (id: string) => void;
  onReactivar: (id: string) => void;
}) {
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(rubro.nombre);
  const [orden, setOrden] = useState(String(rubro.orden));
  const [flujo, setFlujo] = useState<TipoFlujo>(rubro.tipo_flujo);
  const [codigo, setCodigo] = useState(rubro.codigo ?? "");
  const [clase, setClase] = useState<TipoRubro | "">(rubro.tipo ?? "");

  function guardar() {
    const cambios: EditarInput = { id: rubro.id };
    if (nombre.trim() && nombre !== rubro.nombre)
      cambios.nombre = nombre.trim();
    const ordenNum = Number.parseInt(orden, 10);
    if (Number.isInteger(ordenNum) && ordenNum !== rubro.orden)
      cambios.orden = ordenNum;
    if (flujo !== rubro.tipo_flujo) cambios.tipo_flujo = flujo;
    if (codigo.trim() !== (rubro.codigo ?? "")) cambios.codigo = codigo.trim();
    if (clase !== "" && clase !== rubro.tipo) cambios.tipo = clase;
    if (Object.keys(cambios).length > 1) onEditar(cambios);
    setEditando(false);
  }

  if (editando) {
    return (
      <tr className="border-b border-slate-100 bg-turq/5">
        <td className="py-2 pr-4">
          <input
            className="w-16 rounded-md border border-slate-300 px-2 py-1 font-mono"
            value={codigo}
            maxLength={8}
            aria-label={`Código de ${rubro.nombre}`}
            onChange={(e) => setCodigo(e.target.value)}
          />
        </td>
        <td className="py-2 pr-4">
          <input
            className="w-full rounded-md border border-slate-300 px-2 py-1"
            value={nombre}
            aria-label={`Nombre de ${rubro.nombre}`}
            onChange={(e) => setNombre(e.target.value)}
          />
        </td>
        <td className="py-2 pr-4">
          <select
            className="rounded-md border border-slate-300 px-2 py-1"
            value={flujo}
            aria-label={`Naturaleza de ${rubro.nombre}`}
            onChange={(e) => setFlujo(e.target.value as TipoFlujo)}
          >
            <option value="egreso">Egreso</option>
            <option value="ingreso">Ingreso</option>
          </select>
        </td>
        <td className="py-2 pr-4">
          <select
            className="rounded-md border border-slate-300 px-2 py-1"
            value={clase}
            aria-label={`Clase de ${rubro.nombre}`}
            onChange={(e) => setClase(e.target.value as TipoRubro | "")}
          >
            <option value="">—</option>
            <option value="fijo">Fijo</option>
            <option value="variable">Variable</option>
          </select>
        </td>
        <td className="py-2 pr-4 text-right">
          <input
            className="w-16 rounded-md border border-slate-300 px-2 py-1 text-right"
            value={orden}
            inputMode="numeric"
            aria-label={`Orden de ${rubro.nombre}`}
            onChange={(e) => setOrden(e.target.value)}
          />
        </td>
        <td className="py-2 pr-4">
          <EstadoBadge rubro={rubro} />
        </td>
        <td className="flex gap-2 py-2 pr-4">
          <Button size="sm" onClick={guardar}>
            Guardar
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setNombre(rubro.nombre);
              setOrden(String(rubro.orden));
              setFlujo(rubro.tipo_flujo);
              setCodigo(rubro.codigo ?? "");
              setClase(rubro.tipo ?? "");
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
      className={`border-b border-slate-100 ${rubro.activo ? "" : "text-slate-400"}`}
    >
      <td className="py-2 pr-4 font-mono text-slate-500">
        {rubro.codigo ?? "—"}
      </td>
      <td className="py-2 pr-4">{rubro.nombre}</td>
      <td className="py-2 pr-4">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            rubro.tipo_flujo === "ingreso"
              ? "bg-brand-soft/20 text-brand"
              : "bg-slate-100 text-slate-600"
          }`}
        >
          {rubro.tipo_flujo === "ingreso" ? "Ingreso" : "Egreso"}
        </span>
      </td>
      <td className="py-2 pr-4">
        <ClaseBadge tipo={rubro.tipo} />
      </td>
      <td className="py-2 pr-4 text-right font-mono">{rubro.orden}</td>
      <td className="py-2 pr-4">
        <EstadoBadge rubro={rubro} />
      </td>
      {gestiona && (
        <td className="flex gap-2 py-2 pr-4">
          {rubro.es_sistema ? (
            <span className="text-xs italic text-slate-400">Inmutable</span>
          ) : (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setEditando(true)}
              >
                Editar
              </Button>
              {rubro.activo ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onDesactivar(rubro.id)}
                >
                  Desactivar
                </Button>
              ) : (
                <Button size="sm" onClick={() => onReactivar(rubro.id)}>
                  Reactivar
                </Button>
              )}
            </>
          )}
        </td>
      )}
    </tr>
  );
}

function EstadoBadge({ rubro }: { rubro: Rubro }) {
  if (rubro.es_sistema) {
    return (
      <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600">
        Sistema
      </span>
    );
  }
  return rubro.activo ? (
    <span className="rounded-full bg-brand-soft/20 px-2 py-0.5 text-xs font-medium text-brand">
      Activa
    </span>
  ) : (
    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
      Inactiva
    </span>
  );
}

function FormNueva({
  creando,
  onCrear,
}: {
  creando: boolean;
  onCrear: (input: {
    grupo: string;
    nombre: string;
    tipo_flujo: TipoFlujo;
    codigo?: string;
    tipo?: TipoRubro;
  }) => void;
}) {
  const [grupo, setGrupo] = useState("operacion");
  const [nombre, setNombre] = useState("");
  const [flujo, setFlujo] = useState<TipoFlujo>("egreso");
  const [codigo, setCodigo] = useState("");
  const [clase, setClase] = useState<TipoRubro | "">("variable");

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (!nombre.trim()) return;
    onCrear({
      grupo,
      nombre: nombre.trim(),
      tipo_flujo: flujo,
      codigo: codigo.trim() || undefined,
      tipo: clase || undefined,
    });
    setNombre("");
    setCodigo("");
  }

  return (
    <form
      onSubmit={enviar}
      className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 p-4"
    >
      <p className="w-full text-sm font-medium">Nueva categoría</p>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Grupo
        <select
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
          value={grupo}
          onChange={(e) => setGrupo(e.target.value)}
        >
          {Object.entries(GRUPO_LABEL).map(([valor, etiqueta]) => (
            <option key={valor} value={valor}>
              {etiqueta}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Código
        <input
          className="w-20 rounded-md border border-slate-300 px-2 py-1.5 font-mono text-sm text-slate-800"
          value={codigo}
          maxLength={8}
          placeholder="2140"
          onChange={(e) => setCodigo(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Nombre
        <input
          className="w-56 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
          value={nombre}
          maxLength={80}
          onChange={(e) => setNombre(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Naturaleza
        <select
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
          value={flujo}
          onChange={(e) => setFlujo(e.target.value as TipoFlujo)}
        >
          <option value="egreso">Egreso</option>
          <option value="ingreso">Ingreso</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Clase
        <select
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
          value={clase}
          onChange={(e) => setClase(e.target.value as TipoRubro | "")}
        >
          <option value="">—</option>
          <option value="fijo">Fijo</option>
          <option value="variable">Variable</option>
        </select>
      </label>
      <Button type="submit" size="sm" disabled={creando || !nombre.trim()}>
        {creando ? "Creando…" : "Crear"}
      </Button>
    </form>
  );
}
