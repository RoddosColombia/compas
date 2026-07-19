import { Button } from "@/components/ui/button";
import { formatCOP } from "@/lib/money";

export default function App() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-3xl font-bold tracking-tight">COMPAS</h1>
      <p className="text-slate-600">
        Control presupuestal y flujo de caja — RODDOS S.A.S.
      </p>
      <p className="text-sm text-slate-500">
        Esqueleto Sprint 0 · Sesión 1. Ejemplo de formato de monto:{" "}
        <span className="font-mono font-medium">{formatCOP("1234567.89")}</span>
      </p>
      <Button>Todo listo</Button>
    </main>
  );
}
