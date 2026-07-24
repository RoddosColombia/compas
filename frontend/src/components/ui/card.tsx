// Card — superficie base del cockpit (Blueprint §3): blanco, borde hairline,
// esquinas suaves, sombra tenue. Contenedor presentacional; el contenido manda.

import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-hairline bg-surface p-5 shadow-sm",
        className,
      )}
      {...props}
    />
  );
}

export function CardTitle({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2
      className={cn("font-display text-base font-semibold text-ink", className)}
    >
      {children}
    </h2>
  );
}
