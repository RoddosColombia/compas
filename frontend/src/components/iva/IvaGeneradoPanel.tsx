// Pieza 2 (ENTREGA 3) — "Registrar IVA generado del mes". Decisión CEO: el IVA generado
// se carga a mano, agregado, el mes vencido (mes + valor). El backend arma la venta
// VENTAS-YYYY-MM a nombre de RODDOS; el monto del IVA MANDA (no se inventa base, D-13).
//
// Cero aritmética de dinero en el front (regla 1): el valor humano se pasa a canónico
// con `montoACanonico` (decimal.js-light) y viaja como string. El backend deduplica por
// (NIT, numero) → registrar el mismo mes dos veces responde 409 (se muestra el motivo).

import { useState } from "react";

import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { registrarIvaGenerado } from "@/lib/facturas";
import { esMontoHumanoValido, montoACanonico } from "@/lib/unidades";

export function IvaGeneradoPanel({
  onCerrar,
  onRegistrado,
}: {
  onCerrar: () => void;
  /** Tras registrar: refresca liquidación (titular/desglose) Y tabla (§2). */
  onRegistrado: () => void;
}) {
  const [mes, setMes] = useState("");
  const [valor, setValor] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mesValido = /^\d{4}-\d{2}$/.test(mes);
  const valorValido = esMontoHumanoValido(valor);
  const puedeRegistrar = mesValido && valorValido && !enviando;

  async function registrar() {
    if (!puedeRegistrar) return;
    setEnviando(true);
    setError(null);
    try {
      await registrarIvaGenerado(mes, montoACanonico(valor));
      onRegistrado();
      onCerrar();
    } catch (e) {
      // ApiError extiende Error → basta con Error para leer el motivo (p. ej. el 409
      // "ya existe la factura …" del backend cuando el mes ya fue registrado).
      setError(
        e instanceof Error
          ? e.message
          : "No se pudo registrar el IVA generado.",
      );
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <CardTitle>Registrar IVA generado del mes</CardTitle>
        <Button type="button" variant="ghost" size="sm" onClick={onCerrar}>
          Cerrar
        </Button>
      </div>

      <p className="font-sans text-apoyo text-ink-soft">
        Carga el IVA que generaste en un mes ya cerrado. Suma al total del
        período; no reemplaza las facturas de venta que cargues por separado.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <label
          htmlFor="iva-generado-mes"
          className="flex flex-col gap-1 font-sans text-apoyo text-ink-faint"
        >
          <span>Mes</span>
          <input
            id="iva-generado-mes"
            type="month"
            className="w-full rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
            aria-label="Mes del IVA generado"
          />
        </label>
        <label
          htmlFor="iva-generado-valor"
          className="flex flex-col gap-1 font-sans text-apoyo text-ink-faint"
        >
          <span>Valor del IVA</span>
          <input
            id="iva-generado-valor"
            className="w-full rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo tabular"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            aria-label="Valor del IVA generado"
            inputMode="decimal"
            placeholder="8.000.000"
          />
        </label>
      </div>

      {error && <AlertBanner variant="warn">{error}</AlertBanner>}

      <div className="flex gap-2">
        <Button
          type="button"
          variant="cyan"
          size="sm"
          onClick={() => void registrar()}
          disabled={!puedeRegistrar}
        >
          Registrar
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCerrar}>
          Cancelar
        </Button>
      </div>
    </Card>
  );
}
