// EstadoVacio — el patrón que C1/C2 establecieron, formalizado (sistema F1 §5):
// qué falta + enlace al paso siguiente + quién puede hacerlo. Prohibido el
// texto plano sin salida.

import { Link } from "react-router-dom";

export function EstadoVacio({
  mensaje,
  accion,
  quien,
}: {
  /** Qué falta, en lenguaje llano. */
  mensaje: string;
  /** El paso siguiente, siempre accionable. */
  accion?: { to: string; label: string };
  /** Quién puede hacerlo (cuando el lector puede no tener el permiso). */
  quien?: string;
}) {
  return (
    <p className="font-sans text-cuerpo text-ink-soft">
      {mensaje}{" "}
      {accion && (
        <Link to={accion.to} className="font-medium text-cyan hover:underline">
          {accion.label} →
        </Link>
      )}
      {quien && <span className="text-ink-faint"> ({quien})</span>}
    </p>
  );
}
