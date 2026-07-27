// frontend/src/pages/ControlPage.tsx
//
// Presupuesto (vista Control): presupuesto definido vs ejecutado vs disponible por
// rubro y grupo, con semáforo (verde/ámbar/rojo). Selector de mes (solo meses en
// ejecución o cerrados) y vista por categoría / por cuenta. Montos con formatCOP
// (regla 1); el cálculo y el semáforo vienen del backend — el front solo presenta.

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { QueExigeAtencion } from "@/components/control/QueExigeAtencion";
import { PanelDecisiones } from "@/components/decisiones/PanelDecisiones";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card } from "@/components/ui/card";
import { FiltroBarra } from "@/components/ui/filtro-barra";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import {
  BANCO_LABEL,
  type ControlPorCuenta,
  GRUPO_LABEL,
  type Semaforo,
  vistaControl,
  vistaControlPorCuenta,
} from "@/lib/control";
import { listarMeses } from "@/lib/meses";
import { formatCOPEntero } from "@/lib/money";

type Vista = "categoria" | "cuenta" | "decisiones";

const SEMAFORO_ESTILO: Record<Semaforo, string> = {
  verde: "bg-positivo/10 text-positivo",
  amarillo: "bg-atencion/10 text-atencion",
  rojo: "bg-critico/10 text-critico",
};

const SEMAFORO_LABEL: Record<Semaforo, string> = {
  verde: "En rango",
  amarillo: "Cerca del límite",
  rojo: "Sobre-ejecutado",
};

// Segundo canal del semáforo (F1 §0.2: color + símbolo, nunca color solo).
const SEMAFORO_SIMBOLO: Record<Semaforo, string> = {
  verde: "✓",
  amarillo: "●",
  rojo: "✗",
};

export default function ControlPage() {
  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });

  // Solo meses con presupuesto vivo (en ejecución o cerrado), más reciente primero.
  const disponibles = useMemo(() => {
    const items = meses.data?.items ?? [];
    return items
      .filter((m) => m.estado === "en_ejecucion" || m.estado === "cerrado")
      .map((m) => m.mes.slice(0, 7))
      .sort()
      .reverse();
  }, [meses.data]);

  // Mes más reciente con presupuesto pendiente de aprobar (para el vacío accionable).
  const mesPendiente = useMemo(() => {
    const items = meses.data?.items ?? [];
    return (
      items
        .filter((m) => m.estado === "sugerido" || m.estado === "propuesto")
        .map((m) => m.mes.slice(0, 7))
        .sort()
        .reverse()[0] ?? null
    );
  }, [meses.data]);

  const [mesSel, setMesSel] = useState<string | null>(null);
  const mes = mesSel ?? disponibles[0] ?? null;
  const [vista, setVista] = useState<Vista>("categoria");

  const control = useQuery({
    queryKey: ["mes", mes, "control"],
    queryFn: () => vistaControl(mes as string),
    enabled: mes !== null && vista === "categoria",
  });

  const porCuenta = useQuery({
    queryKey: ["mes", mes, "control-por-cuenta"],
    queryFn: () => vistaControlPorCuenta(mes as string),
    enabled: mes !== null && vista === "cuenta",
  });

  const acciones = (
    <FiltroBarra
      filtros={[
        {
          id: "vista",
          label: "Vista",
          opciones: [
            { valor: "categoria", label: "Por categoría" },
            { valor: "cuenta", label: "Por cuenta" },
            { valor: "decisiones", label: "Decisiones" },
          ],
          valor: vista,
          porDefecto: "categoria",
          onChange: (v) => setVista(v as Vista),
        },
        ...(disponibles.length > 0
          ? [
              {
                id: "mes",
                label: "Mes",
                opciones: disponibles.map((m) => ({ valor: m, label: m })),
                valor: mes ?? "",
                porDefecto: disponibles[0],
                onChange: (v: string) => setMesSel(v),
              },
            ]
          : []),
      ]}
    />
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Presupuesto"
        descripcion="Presupuesto definido vs ejecutado por rubro, con semáforo."
        acciones={acciones}
      />

      {vista === "cuenta" && (
        <MatrizPorCuenta
          cargando={porCuenta.isLoading}
          error={porCuenta.isError}
          data={porCuenta.data}
        />
      )}

      {vista === "decisiones" && <PanelDecisiones />}

      {vista !== "decisiones" && meses.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando…</p>
      )}
      {vista !== "decisiones" && meses.data && disponibles.length === 0 && (
        <p className="font-sans text-sm text-ink-soft">
          No hay meses en ejecución o cerrados.{" "}
          {mesPendiente ? (
            <Link
              to={`/meses/${mesPendiente}/presupuesto`}
              className="font-medium text-cyan hover:underline"
            >
              Aprueba el presupuesto de {mesPendiente} →
            </Link>
          ) : (
            <Link to="/meses" className="font-medium text-cyan hover:underline">
              Abre un mes para empezar el ciclo →
            </Link>
          )}
        </p>
      )}

      {vista === "categoria" && control.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando control…</p>
      )}
      {vista === "categoria" && control.isError && (
        <AlertBanner variant="danger">
          No se pudo cargar la Vista Control.
        </AlertBanner>
      )}

      {vista === "categoria" && control.data && (
        <>
          {/* C2: desvíos priorizados por plata, arriba del detalle */}
          <QueExigeAtencion
            grupos={control.data.grupos}
            mes={mes as string}
            conAnchors
          />

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiTileV2
              label="Caja disponible"
              valor={control.data.caja_disponible}
              contexto="caja del libro a hoy"
            />
            <KpiTileV2
              label="Presupuesto definido"
              valor={control.data.total.definido}
              contexto="aprobado para el mes"
            />
            <KpiTileV2
              label="Ejecutado"
              valor={control.data.total.ejecutado}
              contexto="gastado en lo corrido del mes"
            />
            <KpiTileV2
              label="Disponible"
              valor={control.data.total.disponible}
              contexto="lo que queda del presupuesto aprobado"
            />
          </div>

          <Card className="overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="w-full font-sans text-sm">
                <thead>
                  <tr className="border-b border-hairline text-left text-ink-faint">
                    <th className="px-4 py-2.5 font-semibold">Rubro</th>
                    <th className="px-4 py-2.5 text-right font-semibold">
                      Definido
                    </th>
                    <th className="px-4 py-2.5 text-right font-semibold">
                      Ejecutado
                    </th>
                    <th className="px-4 py-2.5 text-right font-semibold">
                      Disponible
                    </th>
                    <th className="px-4 py-2.5 text-right font-semibold">
                      % ejec.
                    </th>
                    <th className="px-4 py-2.5 font-semibold">Semáforo</th>
                  </tr>
                </thead>
                <tbody>
                  {control.data.grupos.map((g) => (
                    <GrupoBloque key={g.grupo} grupo={g} />
                  ))}
                  <tr className="border-t-2 border-hairline font-semibold text-ink">
                    <td className="px-4 py-2.5">Total</td>
                    <td className="tabular px-4 py-2.5 text-right">
                      {formatCOPEntero(control.data.total.definido)}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right">
                      {formatCOPEntero(control.data.total.ejecutado)}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right">
                      {formatCOPEntero(control.data.total.disponible)}
                    </td>
                    <td className="px-4 py-2.5" />
                    <td className="px-4 py-2.5" />
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>

          {control.data.sin_presupuesto.length > 0 && (
            <AlertBanner variant="warn">
              <span className="font-semibold">Sin presupuesto:</span> gastos en
              rubros sin línea definida este mes —{" "}
              {control.data.sin_presupuesto
                .map((s) => `${s.rubro} (${formatCOPEntero(s.ejecutado)})`)
                .join(" · ")}
            </AlertBanner>
          )}
        </>
      )}
    </div>
  );
}

function MatrizPorCuenta({
  cargando,
  error,
  data,
}: {
  cargando: boolean;
  error: boolean;
  data: ControlPorCuenta | undefined;
}) {
  if (cargando)
    return (
      <p className="font-sans text-sm text-ink-soft">Cargando por cuenta…</p>
    );
  if (error)
    return (
      <AlertBanner variant="danger">
        No se pudo cargar la vista por cuenta.
      </AlertBanner>
    );
  if (!data) return null;
  if (data.bancos.length === 0)
    return (
      <p className="font-sans text-sm text-ink-soft">
        Aún no hay egresos con banco en este mes.
      </p>
    );

  const bancos = data.bancos;
  return (
    <>
      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-4 py-2.5 font-semibold">Rubro</th>
                {bancos.map((b) => (
                  <th key={b} className="px-4 py-2.5 text-right font-semibold">
                    {BANCO_LABEL[b] ?? b}
                  </th>
                ))}
                <th className="px-4 py-2.5 text-right font-semibold">Total</th>
              </tr>
            </thead>
            <tbody>
              {data.grupos.map((g) => (
                <MatrizGrupo key={g.grupo} grupo={g} bancos={bancos} />
              ))}
              <tr className="border-t-2 border-hairline font-semibold text-ink">
                <td className="px-4 py-2.5">Total</td>
                {bancos.map((b) => (
                  <td key={b} className="tabular px-4 py-2.5 text-right">
                    {formatCOPEntero(data.total.por_banco[b])}
                  </td>
                ))}
                <td className="tabular px-4 py-2.5 text-right">
                  {formatCOPEntero(data.total.total)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      {data.sin_presupuesto.length > 0 && (
        <AlertBanner variant="warn">
          <span className="font-semibold">Sin presupuesto:</span>{" "}
          {data.sin_presupuesto
            .map(
              (s) =>
                `${s.rubro} (${bancos
                  .filter((b) => s.por_banco[b] && s.por_banco[b] !== "0.00")
                  .map(
                    (b) =>
                      `${BANCO_LABEL[b] ?? b} ${formatCOPEntero(s.por_banco[b])}`,
                  )
                  .join(", ")})`,
            )
            .join(" · ")}
        </AlertBanner>
      )}
    </>
  );
}

function MatrizGrupo({
  grupo,
  bancos,
}: {
  grupo: import("@/lib/control").ControlCuentaGrupo;
  bancos: string[];
}) {
  return (
    <>
      <tr className="bg-surface-muted">
        <td
          colSpan={bancos.length + 2}
          className="px-4 py-1.5 font-sans text-apoyo font-semibold tracking-wide text-ink-faint uppercase"
        >
          {GRUPO_LABEL[grupo.grupo] ?? grupo.grupo}
        </td>
      </tr>
      {grupo.lineas.map((l) => (
        <tr key={l.rubro_id} className="border-b border-hairline/60">
          <td className="px-4 py-2 text-ink">{l.rubro}</td>
          {bancos.map((b) => (
            <td key={b} className="tabular px-4 py-2 text-right text-ink-soft">
              {formatCOPEntero(l.por_banco[b])}
            </td>
          ))}
          <td className="tabular px-4 py-2 text-right font-medium text-ink">
            {formatCOPEntero(l.total)}
          </td>
        </tr>
      ))}
      <tr className="border-b border-hairline text-ink-faint">
        <td className="px-4 py-1.5 text-right text-apoyo italic">Subtotal</td>
        {bancos.map((b) => (
          <td key={b} className="tabular px-4 py-1.5 text-right text-apoyo">
            {formatCOPEntero(grupo.subtotal.por_banco[b])}
          </td>
        ))}
        <td className="tabular px-4 py-1.5 text-right text-apoyo">
          {formatCOPEntero(grupo.subtotal.total)}
        </td>
      </tr>
    </>
  );
}

function GrupoBloque({
  grupo,
}: {
  grupo: import("@/lib/control").ControlGrupo;
}) {
  return (
    <>
      <tr className="bg-surface-muted">
        <td
          colSpan={6}
          className="px-4 py-1.5 font-sans text-apoyo font-semibold tracking-wide text-ink-faint uppercase"
        >
          {GRUPO_LABEL[grupo.grupo] ?? grupo.grupo}
        </td>
      </tr>
      {grupo.lineas.map((l) => (
        // id por fila = anchor de "Qué exige atención"; target: resalta la fila.
        <tr
          key={l.rubro_id}
          id={`rubro-${l.rubro_id}`}
          className="scroll-mt-16 border-b border-hairline/60 target:bg-atencion/10"
        >
          <td className="px-4 py-2 text-ink">{l.rubro}</td>
          <td className="tabular px-4 py-2 text-right text-ink-soft">
            {formatCOPEntero(l.definido)}
          </td>
          <td className="tabular px-4 py-2 text-right text-ink-soft">
            {formatCOPEntero(l.ejecutado)}
          </td>
          <td className="tabular px-4 py-2 text-right text-ink-soft">
            {formatCOPEntero(l.disponible)}
          </td>
          <td className="tabular px-4 py-2 text-right text-ink-soft">
            {l.pct_ejecutado === null ? "—" : `${l.pct_ejecutado}%`}
          </td>
          <td className="px-4 py-2">
            <span
              className={`rounded-full px-2 py-0.5 font-sans text-apoyo font-medium whitespace-nowrap ${SEMAFORO_ESTILO[l.semaforo]}`}
            >
              {SEMAFORO_SIMBOLO[l.semaforo]} {SEMAFORO_LABEL[l.semaforo]}
            </span>
          </td>
        </tr>
      ))}
      <tr className="border-b border-hairline text-ink-faint">
        <td className="px-4 py-1.5 text-right text-apoyo italic">Subtotal</td>
        <td className="tabular px-4 py-1.5 text-right text-apoyo">
          {formatCOPEntero(grupo.subtotal.definido)}
        </td>
        <td className="tabular px-4 py-1.5 text-right text-apoyo">
          {formatCOPEntero(grupo.subtotal.ejecutado)}
        </td>
        <td className="tabular px-4 py-1.5 text-right text-apoyo">
          {formatCOPEntero(grupo.subtotal.disponible)}
        </td>
        <td className="px-4 py-1.5" />
        <td className="px-4 py-1.5" />
      </tr>
    </>
  );
}
