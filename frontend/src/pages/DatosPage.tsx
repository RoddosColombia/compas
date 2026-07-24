// frontend/src/pages/DatosPage.tsx
//
// Datos — la vista de CAPTURA del cockpit (Blueprint): los supuestos que alimentan
// el motor (parámetros de proyección) y el catálogo administrable de modelos de
// moto. Es el cimiento de la predicción: sin supuestos ni modelos, no hay caja
// proyectada. Montos como STRING (regla 1; nunca Number). Las mutaciones las
// autoriza el backend con proyeccion:gestionar; el front esconde controles según
// capacidades (regla 9). Al guardar se invalida la proyección (Inicio/Proyecciones
// se refrescan solos).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api";
import {
  type ModeloCrearInput,
  type ModeloMoto,
  crearModelo,
  desactivarModelo,
  listarModelos,
  reactivarModelo,
} from "@/lib/modelosMoto";
import { formatCOP } from "@/lib/money";
import {
  PARAMS_INT,
  type Parametros,
  type ParametrosInput,
  guardarParametros,
  obtenerParametros,
} from "@/lib/parametros";

// ── Metadatos de los supuestos (una sola definición para el formulario) ──
type CampoTipo = "money" | "tasa" | "int" | "dias" | "meses";
interface Campo {
  key: string;
  label: string;
  tipo: CampoTipo;
  hint?: string;
}
interface Grupo {
  titulo: string;
  campos: Campo[];
}

const GRUPOS_PARAMS: Grupo[] = [
  {
    titulo: "Caja",
    campos: [
      { key: "caja_inicial", label: "Caja inicial", tipo: "money" },
      { key: "caja_minima", label: "Umbral (caja mínima)", tipo: "money" },
    ],
  },
  {
    titulo: "Colocación",
    campos: [
      { key: "motos_base", label: "Motos base / mes", tipo: "int" },
      {
        key: "crec_pct_mensual",
        label: "Crecimiento mensual",
        tipo: "tasa",
        hint: "decimal (0.01 = 1%/mes)",
      },
      { key: "horizonte_meses", label: "Horizonte", tipo: "meses" },
    ],
  },
  {
    titulo: "Inventario Auteco",
    campos: [
      { key: "adelanto_auteco", label: "Adelanto por moto", tipo: "money" },
      { key: "plazo_auteco_dias", label: "Plazo de pago", tipo: "dias" },
      { key: "base_auteco_dias", label: "Base de fondeo", tipo: "dias" },
      {
        key: "tasa_auteco",
        label: "Tasa de fondeo",
        tipo: "tasa",
        hint: "decimal (0.016 = 1.6%)",
      },
    ],
  },
  {
    titulo: "Operación",
    campos: [
      { key: "gastos_fijos", label: "Gastos fijos / mes", tipo: "money" },
      { key: "gps_moto", label: "GPS por moto", tipo: "money" },
      { key: "costo_moto_nueva", label: "Costo moto nueva", tipo: "money" },
    ],
  },
  {
    titulo: "Deuda",
    campos: [
      { key: "deuda", label: "Cuota de deuda", tipo: "money" },
      {
        key: "tasa_deuda",
        label: "Tasa de deuda",
        tipo: "tasa",
        hint: "decimal (0.011 = 1.1%)",
      },
      { key: "mes_inicio_deuda", label: "Mes de inicio", tipo: "int" },
      { key: "meses_deuda", label: "Nº de meses", tipo: "int" },
    ],
  },
  {
    titulo: "Cartera y mora",
    campos: [
      {
        key: "pct_mora",
        label: "Mora",
        tipo: "tasa",
        hint: "decimal (0.03 = 3%)",
      },
      {
        key: "pct_recuperacion",
        label: "Recuperación",
        tipo: "tasa",
        hint: "decimal (0.40 = 40%)",
      },
      { key: "pct_default", label: "Default", tipo: "tasa", hint: "decimal" },
      {
        key: "pct_provision",
        label: "Provisión (NIIF 9)",
        tipo: "tasa",
        hint: "informativa; fuera de la caja",
      },
    ],
  },
];

const INT_KEYS = new Set<string>(PARAMS_INT);

export default function DatosPage() {
  const { puede } = useAuth();
  const puedeGestionar = puede("proyeccion:gestionar");

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Datos"
        descripcion="Los supuestos y modelos que alimentan la proyección. Es el cimiento: sin ellos no hay caja proyectada."
      />
      <ParametrosPanel puedeGestionar={puedeGestionar} />
      <ModelosPanel puedeGestionar={puedeGestionar} />
      <OtrasCapturas />
    </div>
  );
}

// Herramientas de captura que ya existen (movimientos, cargas bancarias, catálogos).
// Se reubicarán en su lugar definitivo; por ahora viven aquí para no perder acceso.
const HERRAMIENTAS = [
  { label: "Caja del mes", path: "/caja" },
  { label: "Cargas bancarias", path: "/cargas" },
  { label: "Categorías", path: "/categorias" },
  { label: "Reglas", path: "/reglas" },
  { label: "Meses", path: "/meses" },
];

function OtrasCapturas() {
  return (
    <Card>
      <CardTitle>Otras capturas</CardTitle>
      <div className="mt-3 flex flex-wrap gap-2">
        {HERRAMIENTAS.map((h) => (
          <Link
            key={h.path}
            to={h.path}
            className="rounded-lg border border-hairline bg-surface px-3 py-2 font-sans text-sm font-medium text-ink transition-colors hover:border-cyan hover:text-cyan"
          >
            {h.label}
          </Link>
        ))}
      </div>
    </Card>
  );
}

// ── Panel de supuestos (parámetros del motor) ──
function ParametrosPanel({ puedeGestionar }: { puedeGestionar: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["parametros"], queryFn: obtenerParametros });
  const [form, setForm] = useState<Record<string, string>>({});

  // Precarga el formulario con lo vigente cuando llega (o queda vacío si no hay).
  useEffect(() => {
    if (q.data) {
      const inicial: Record<string, string> = {
        vigente_desde: q.data.vigente_desde,
      };
      for (const g of GRUPOS_PARAMS) {
        for (const c of g.campos) {
          inicial[c.key] = String(
            (q.data as Parametros)[c.key as keyof Parametros],
          );
        }
      }
      setForm(inicial);
    }
  }, [q.data]);

  const mut = useMutation({
    mutationFn: guardarParametros,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["parametros"] });
      qc.invalidateQueries({ queryKey: ["proyeccion"] });
    },
  });

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const input = { vigente_desde: form.vigente_desde } as Record<
      string,
      string | number
    >;
    for (const g of GRUPOS_PARAMS) {
      for (const c of g.campos) {
        input[c.key] = INT_KEYS.has(c.key)
          ? Number(form[c.key])
          : (form[c.key] ?? "");
      }
    }
    mut.mutate(input as unknown as ParametrosInput);
  }

  return (
    <Card>
      <CardTitle>Supuestos del motor</CardTitle>
      {q.isLoading && (
        <p className="mt-2 font-sans text-sm text-ink-soft">
          Cargando supuestos…
        </p>
      )}
      {q.data === null && !q.isLoading && (
        <p className="mt-2 font-sans text-sm text-ink-soft">
          Aún no hay supuestos configurados. Captúralos para habilitar la
          proyección.
        </p>
      )}

      <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-5">
        {/* Vigencia */}
        <div className="max-w-xs">
          <CampoInput
            label="Vigente desde"
            type="date"
            value={form.vigente_desde ?? ""}
            onChange={(v) => set("vigente_desde", v)}
            disabled={!puedeGestionar}
          />
        </div>

        {GRUPOS_PARAMS.map((g) => (
          <fieldset key={g.titulo} className="flex flex-col gap-2">
            <legend className="font-sans text-xs font-semibold tracking-wider text-ink-faint uppercase">
              {g.titulo}
            </legend>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {g.campos.map((c) => (
                <CampoInput
                  key={c.key}
                  label={c.label}
                  hint={c.hint}
                  inputMode={
                    c.tipo === "money" || c.tipo === "tasa"
                      ? "decimal"
                      : "numeric"
                  }
                  value={form[c.key] ?? ""}
                  onChange={(v) => set(c.key, v)}
                  disabled={!puedeGestionar}
                />
              ))}
            </div>
          </fieldset>
        ))}

        {mut.isError && (
          <AlertBanner variant="danger">
            {mut.error instanceof ApiError
              ? mut.error.message
              : "No se pudieron guardar los supuestos."}
          </AlertBanner>
        )}
        {mut.isSuccess && (
          <AlertBanner variant="ok">Supuestos guardados.</AlertBanner>
        )}

        {puedeGestionar && (
          <div>
            <Button type="submit" variant="cyan" disabled={mut.isPending}>
              {mut.isPending ? "Guardando…" : "Guardar supuestos"}
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

// ── Panel de modelos de moto ──
const MODELO_VACIO: ModeloCrearInput = {
  nombre: "",
  costo_auteco: "",
  precio_venta_con_iva: "",
  cuota_inicial: "",
  cuota_semanal: "",
  plazo_semanas: 0,
  matricula: "",
  participacion_mix: "",
};

function ModelosPanel({ puedeGestionar }: { puedeGestionar: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["modelos-moto"],
    queryFn: () => listarModelos(),
  });
  const [nuevo, setNuevo] = useState<ModeloCrearInput>(MODELO_VACIO);

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["modelos-moto"] });
    qc.invalidateQueries({ queryKey: ["proyeccion"] });
  };
  const crear = useMutation({
    mutationFn: crearModelo,
    onSuccess: () => {
      invalidar();
      setNuevo(MODELO_VACIO);
    },
  });
  const desactivar = useMutation({
    mutationFn: desactivarModelo,
    onSuccess: invalidar,
  });
  const reactivar = useMutation({
    mutationFn: reactivarModelo,
    onSuccess: invalidar,
  });

  const setN = (k: keyof ModeloCrearInput, v: string) =>
    setNuevo((m) => ({
      ...m,
      [k]: k === "plazo_semanas" ? Number(v) : v,
    }));

  return (
    <Card>
      <CardTitle>Modelos de moto</CardTitle>
      <p className="mt-0.5 font-sans text-xs text-ink-faint">
        Cada modelo aporta al mix con su cuota, plazo y cuota inicial.
      </p>

      {q.isLoading && (
        <p className="mt-3 font-sans text-sm text-ink-soft">
          Cargando modelos…
        </p>
      )}

      {q.data && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-3 py-2 font-semibold">Modelo</th>
                <th className="px-3 py-2 text-right font-semibold">
                  Cuota sem.
                </th>
                <th className="px-3 py-2 text-right font-semibold">
                  Cuota inicial
                </th>
                <th className="px-3 py-2 text-right font-semibold">Plazo</th>
                <th className="px-3 py-2 text-right font-semibold">Mix</th>
                <th className="px-3 py-2 font-semibold">Estado</th>
                {puedeGestionar && <th className="px-3 py-2" />}
              </tr>
            </thead>
            <tbody>
              {q.data.map((m) => (
                <ModeloFila
                  key={m.id}
                  m={m}
                  puedeGestionar={puedeGestionar}
                  onDesactivar={() => desactivar.mutate(m.id)}
                  onReactivar={() => reactivar.mutate(m.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {puedeGestionar && (
        <form
          className="mt-5 border-t border-hairline pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            crear.mutate(nuevo);
          }}
        >
          <p className="mb-2 font-sans text-xs font-semibold tracking-wider text-ink-faint uppercase">
            Agregar modelo
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <CampoInput
              label="Nombre"
              value={nuevo.nombre}
              onChange={(v) => setN("nombre", v)}
            />
            <CampoInput
              label="Cuota semanal"
              inputMode="decimal"
              value={nuevo.cuota_semanal}
              onChange={(v) => setN("cuota_semanal", v)}
            />
            <CampoInput
              label="Cuota inicial"
              inputMode="decimal"
              value={nuevo.cuota_inicial}
              onChange={(v) => setN("cuota_inicial", v)}
            />
            <CampoInput
              label="Plazo (semanas)"
              inputMode="numeric"
              value={nuevo.plazo_semanas ? String(nuevo.plazo_semanas) : ""}
              onChange={(v) => setN("plazo_semanas", v)}
            />
            <CampoInput
              label="Costo Auteco"
              inputMode="decimal"
              value={nuevo.costo_auteco}
              onChange={(v) => setN("costo_auteco", v)}
            />
            <CampoInput
              label="Precio venta (con IVA)"
              inputMode="decimal"
              value={nuevo.precio_venta_con_iva}
              onChange={(v) => setN("precio_venta_con_iva", v)}
            />
            <CampoInput
              label="Matrícula"
              inputMode="decimal"
              value={nuevo.matricula}
              onChange={(v) => setN("matricula", v)}
            />
            <CampoInput
              label="Participación mix"
              hint="decimal (0.5 = 50%)"
              inputMode="decimal"
              value={nuevo.participacion_mix}
              onChange={(v) => setN("participacion_mix", v)}
            />
          </div>
          {crear.isError && (
            <div className="mt-3">
              <AlertBanner variant="danger">
                {crear.error instanceof ApiError
                  ? crear.error.message
                  : "No se pudo crear el modelo."}
              </AlertBanner>
            </div>
          )}
          <div className="mt-3">
            <Button type="submit" variant="cyan" disabled={crear.isPending}>
              {crear.isPending ? "Agregando…" : "Agregar modelo"}
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function ModeloFila({
  m,
  puedeGestionar,
  onDesactivar,
  onReactivar,
}: {
  m: ModeloMoto;
  puedeGestionar: boolean;
  onDesactivar: () => void;
  onReactivar: () => void;
}) {
  return (
    <tr className="border-b border-hairline/60 last:border-0">
      <td className="px-3 py-2 font-medium text-ink">
        {m.nombre}
        {m.es_sistema && (
          <span className="ml-2 rounded bg-surface-muted px-1.5 py-0.5 font-sans text-[10px] text-ink-faint">
            sistema
          </span>
        )}
      </td>
      <td className="tabular px-3 py-2 text-right text-ink-soft">
        {formatCOP(m.cuota_semanal)}
      </td>
      <td className="tabular px-3 py-2 text-right text-ink-soft">
        {formatCOP(m.cuota_inicial)}
      </td>
      <td className="tabular px-3 py-2 text-right text-ink-soft">
        {m.plazo_semanas} sem
      </td>
      <td className="tabular px-3 py-2 text-right text-ink-soft">
        {m.participacion_mix}
      </td>
      <td className="px-3 py-2">
        <span
          className={`rounded-full px-2 py-0.5 font-sans text-xs font-medium ${
            m.activo
              ? "bg-green/10 text-green"
              : "bg-surface-muted text-ink-faint"
          }`}
        >
          {m.activo ? "Activo" : "Inactivo"}
        </span>
      </td>
      {puedeGestionar && (
        <td className="px-3 py-2 text-right">
          {m.activo ? (
            <Button variant="ghost" size="sm" onClick={onDesactivar}>
              Desactivar
            </Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={onReactivar}>
              Reactivar
            </Button>
          )}
        </td>
      )}
    </tr>
  );
}

// ── Input reutilizable (etiqueta + campo hairline) ──
function CampoInput({
  label,
  hint,
  value,
  onChange,
  type = "text",
  inputMode,
  disabled,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  inputMode?: "decimal" | "numeric";
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-sans text-xs font-medium text-ink-soft">
        {label}
      </span>
      <input
        type={type}
        inputMode={inputMode}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="tabular rounded-md border border-hairline bg-surface px-3 py-1.5 font-sans text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan disabled:bg-surface-muted disabled:text-ink-faint"
      />
      {hint && (
        <span className="font-sans text-[10px] text-ink-faint">{hint}</span>
      )}
    </label>
  );
}
