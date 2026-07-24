// ScenarioChip — pill de selección de escenario (Blueprint §3).
// Activo = pill negra (tinta); inactivo = borde hairline. Es un toggle → aria-pressed.

import { cn } from "@/lib/utils";

export interface ScenarioChipProps {
  label: string;
  active: boolean;
  onClick: () => void;
  className?: string;
}

export function ScenarioChip({
  label,
  active,
  onClick,
  className,
}: ScenarioChipProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "rounded-full px-4 py-1.5 font-sans text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan",
        active
          ? "bg-ink text-white"
          : "border border-hairline bg-surface text-ink-soft hover:border-ink/30 hover:text-ink",
        className,
      )}
    >
      {label}
    </button>
  );
}
