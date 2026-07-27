// ErrorEstado — sistema F1 §5: qué pasó en lenguaje llano + reintentar +
// "si persiste, avisa a Andrés". Nunca un código pelado.

import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";

export function ErrorEstado({
  mensaje,
  onReintentar,
}: {
  mensaje: string;
  onReintentar?: () => void;
}) {
  return (
    <AlertBanner variant="danger">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>
          {mensaje}{" "}
          <span className="font-normal">Si persiste, avisa a Andrés.</span>
        </span>
        {onReintentar && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onReintentar}
          >
            Reintentar
          </Button>
        )}
      </div>
    </AlertBanner>
  );
}
