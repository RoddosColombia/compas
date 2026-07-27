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
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
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

const INPUT_CLASS =
  "rounded-md border border-hairline bg-surface px-3 py-1.5 font-sans text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan";

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
      <PageHeader
        titulo="Categorías"
        descripcion="El plan de cuentas del presupuesto — código, grupo y clase (fijo/variable)"
      />

      {mensaje && <AlertBanner variant="danger">{mensaje}</AlertBanner>}

      {rubros.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando categorías…</p>
      )}
      {rubros.isError && (
        <AlertBanner variant="danger">
          No se pudieron cargar las categorías.
        </AlertBanner>
      )}

      {grupos && (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full font-sans text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-ink-faint">
                  <th className="px-4 py-2.5 font-semibold">Código</th>
                  <th className="px-4 py-2.5 font-semibold">Categoría</th>
                  <th className="px-4 py-2.5 font-semibold">Naturaleza</th>
                  <th className="px-4 py-2.5 font-semibold">Clase</th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Orden
                  </th>
                  <th className="px-4 py-2.5 font-semibold">Estado</th>
                  {gestiona && (
                    <th className="px-4 py-2.5 font-semibold">Acciones</th>
                  )}
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
        </Card>
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
      <tr className="bg-surface-muted">
        <td
          colSpan={cols}
          className="px-4 py-1.5 font-sans text-apoyo font-semibold tracking-wide text-ink-faint uppercase"
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
  if (tipo === null)
    return <span className="text-apoyo text-ink-faint">—</span>;
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-apoyo font-medium ${
        tipo === "fijo"
          ? "bg-surface-muted text-ink-soft"
          : "bg-cyan/10 text-cyan"
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
      <tr className="border-b border-hairline/60 bg-cyan/5">
        <td className="px-4 py-2">
          <input
            className={`${INPUT_CLASS} tabular w-16`}
            value={codigo}
            maxLength={8}
            aria-label={`Código de ${rubro.nombre}`}
            onChange={(e) => setCodigo(e.target.value)}
          />
        </td>
        <td className="px-4 py-2">
          <input
            className={`${INPUT_CLASS} w-full`}
            value={nombre}
            aria-label={`Nombre de ${rubro.nombre}`}
            onChange={(e) => setNombre(e.target.value)}
          />
        </td>
        <td className="px-4 py-2">
          <select
            className={INPUT_CLASS}
            value={flujo}
            aria-label={`Naturaleza de ${rubro.nombre}`}
            onChange={(e) => setFlujo(e.target.value as TipoFlujo)}
          >
            <option value="egreso">Egreso</option>
            <option value="ingreso">Ingreso</option>
          </select>
        </td>
        <td className="px-4 py-2">
          <select
            className={INPUT_CLASS}
            value={clase}
            aria-label={`Clase de ${rubro.nombre}`}
            onChange={(e) => setClase(e.target.value as TipoRubro | "")}
          >
            <option value="">—</option>
            <option value="fijo">Fijo</option>
            <option value="variable">Variable</option>
          </select>
        </td>
        <td className="px-4 py-2 text-right">
          <input
            className={`${INPUT_CLASS} tabular w-16 text-right`}
            value={orden}
            inputMode="numeric"
            aria-label={`Orden de ${rubro.nombre}`}
            onChange={(e) => setOrden(e.target.value)}
          />
        </td>
        <td className="px-4 py-2">
          <EstadoBadge rubro={rubro} />
        </td>
        <td className="flex gap-2 px-4 py-2">
          <Button size="sm" variant="cyan" onClick={guardar}>
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
      className={`border-b border-hairline/60 ${rubro.activo ? "" : "text-ink-faint"}`}
    >
      <td className="tabular px-4 py-2 text-ink-soft">{rubro.codigo ?? "—"}</td>
      <td className="px-4 py-2 text-ink">{rubro.nombre}</td>
      <td className="px-4 py-2">
        <span
          className={`rounded-full px-2 py-0.5 text-apoyo font-medium ${
            rubro.tipo_flujo === "ingreso"
              ? "bg-positivo/10 text-positivo"
              : "bg-surface-muted text-ink-soft"
          }`}
        >
          {rubro.tipo_flujo === "ingreso" ? "Ingreso" : "Egreso"}
        </span>
      </td>
      <td className="px-4 py-2">
        <ClaseBadge tipo={rubro.tipo} />
      </td>
      <td className="tabular px-4 py-2 text-right">{rubro.orden}</td>
      <td className="px-4 py-2">
        <EstadoBadge rubro={rubro} />
      </td>
      {gestiona && (
        <td className="flex gap-2 px-4 py-2">
          {rubro.es_sistema ? (
            <span className="text-apoyo italic text-ink-faint">Inmutable</span>
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
                <Button
                  size="sm"
                  variant="cyan"
                  onClick={() => onReactivar(rubro.id)}
                >
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
      <span className="rounded-full bg-surface-muted px-2 py-0.5 text-apoyo font-medium text-ink-soft">
        Sistema
      </span>
    );
  }
  return rubro.activo ? (
    <span className="rounded-full bg-positivo/10 px-2 py-0.5 text-apoyo font-medium text-positivo">
      Activa
    </span>
  ) : (
    <span className="rounded-full bg-surface-muted px-2 py-0.5 text-apoyo font-medium text-ink-faint">
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
    <Card>
      <form onSubmit={enviar} className="flex flex-wrap items-end gap-3">
        <CardTitle className="w-full">Nueva categoría</CardTitle>
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Grupo
          <select
            className={INPUT_CLASS}
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
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Código
          <input
            className={`${INPUT_CLASS} tabular w-20`}
            value={codigo}
            maxLength={8}
            placeholder="2140"
            onChange={(e) => setCodigo(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Nombre
          <input
            className={`${INPUT_CLASS} w-56`}
            value={nombre}
            maxLength={80}
            onChange={(e) => setNombre(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Naturaleza
          <select
            className={INPUT_CLASS}
            value={flujo}
            onChange={(e) => setFlujo(e.target.value as TipoFlujo)}
          >
            <option value="egreso">Egreso</option>
            <option value="ingreso">Ingreso</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
          Clase
          <select
            className={INPUT_CLASS}
            value={clase}
            onChange={(e) => setClase(e.target.value as TipoRubro | "")}
          >
            <option value="">—</option>
            <option value="fijo">Fijo</option>
            <option value="variable">Variable</option>
          </select>
        </label>
        <Button
          type="submit"
          variant="cyan"
          size="sm"
          disabled={creando || !nombre.trim()}
        >
          {creando ? "Creando…" : "Crear"}
        </Button>
      </form>
    </Card>
  );
}
