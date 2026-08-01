// frontend/src/pages/IvaPage.tsx
//
// Pantalla de IVA (/iva) — spec de diseño E2 v1.1. Responde: "¿cuánto voy a pagar de
// IVA el próximo período, y qué me falta cargar para que la cifra sea confiable?".
// Un scroll, cuatro bloques (§3): titular → qué exige atención → liquidación → tabla.
// TODO el cálculo lo hace el backend (regla 1): los montos son string → formatCOP.
//
// §2 (regla que gobierna la pantalla): tras marcar deducibilidad (individual o lote),
// se recalcula la LIQUIDACIÓN COMPLETA (titular + desglose + qué exige atención), no
// solo la tabla → `refrescarTodo` invalida ambas queries.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CargaPanel } from "@/components/iva/CargaPanel";
import { FacturasTabla } from "@/components/iva/FacturasTabla";
import { IvaGeneradoPanel } from "@/components/iva/IvaGeneradoPanel";
import { LiquidacionCard } from "@/components/iva/LiquidacionCard";
import { TitularIva } from "@/components/iva/TitularIva";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ErrorEstado } from "@/components/ui/error-estado";
import { listarFacturas } from "@/lib/facturas";
import { obtenerLiquidacionIva } from "@/lib/iva";

export default function IvaPage() {
  const qc = useQueryClient();
  const [mostrarCarga, setMostrarCarga] = useState(false);
  const [mostrarGenerado, setMostrarGenerado] = useState(false);

  const liq = useQuery({
    queryKey: ["iva", "liquidacion"],
    queryFn: obtenerLiquidacionIva,
  });
  const facturas = useQuery({
    queryKey: ["facturas", "todas"],
    queryFn: () => listarFacturas(),
  });

  // §2: una sola acción recalcula liquidación (titular/desglose/atención) Y tabla.
  const refrescarTodo = () => {
    void qc.invalidateQueries({ queryKey: ["iva", "liquidacion"] });
    void qc.invalidateQueries({ queryKey: ["facturas"] });
  };

  // "Registrar IVA generado del mes" está SIEMPRE disponible (incluso sin facturas):
  // es la carga mensual del CEO. "Cargar facturas" duplica el CTA del estado vacío,
  // así que solo aparece cuando ya hay facturas.

  const cargando = liq.isLoading || facturas.isLoading;
  const hayError = liq.isError || facturas.isError;
  const vacio = (facturas.data?.length ?? 0) === 0;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="IVA"
        descripcion="Cuánto pagarías de IVA el próximo período y qué falta cargar para que la cifra sea confiable."
        acciones={
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setMostrarGenerado(true)}
            >
              Registrar IVA generado del mes
            </Button>
            {!vacio && (
              <Button
                type="button"
                variant="cyan"
                onClick={() => setMostrarCarga(true)}
              >
                Cargar facturas
              </Button>
            )}
          </div>
        }
      />

      {mostrarGenerado && (
        <IvaGeneradoPanel
          onCerrar={() => setMostrarGenerado(false)}
          onRegistrado={refrescarTodo}
        />
      )}

      {mostrarCarga && (
        <CargaPanel
          onCerrar={() => setMostrarCarga(false)}
          onCargado={refrescarTodo}
        />
      )}

      {cargando && <Cargando variante="card" />}

      {hayError && (
        <ErrorEstado
          mensaje="No se pudo cargar la información de IVA."
          onReintentar={() => {
            void liq.refetch();
            void facturas.refetch();
          }}
        />
      )}

      {!cargando && !hayError && vacio && !mostrarCarga && (
        <Card className="flex flex-col items-center gap-3 py-12 text-center">
          <p className="font-display text-cifra-sm font-semibold text-ink">
            Aún no hay facturas cargadas
          </p>
          <p className="max-w-md font-sans text-cuerpo text-ink-soft">
            Con ellas verás cuánto pagarías de IVA este cuatrimestre y cuándo.
          </p>
          <Button
            type="button"
            variant="cyan"
            onClick={() => setMostrarCarga(true)}
          >
            Cargar facturas
          </Button>
        </Card>
      )}

      {!cargando && !hayError && !vacio && liq.data && (
        // Orden de razonamiento del §3: titular (§3①) → liquidación (§3③) → tabla
        // (§4). El bloque "qué exige atención" (§2) es la pieza 6, tras el deploy.
        <>
          <TitularIva liquidacion={liq.data} facturas={facturas.data ?? []} />
          <LiquidacionCard liquidacion={liq.data} />
          <FacturasTabla
            facturas={facturas.data ?? []}
            onCambio={refrescarTodo}
          />
        </>
      )}
    </div>
  );
}
