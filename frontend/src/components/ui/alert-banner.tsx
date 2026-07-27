// AlertBanner — franja de estado del cockpit (Blueprint §3).
// danger (rojo) = perforación de caja: es urgente → role=alert.
// ok/warn no son urgentes → role=status. El rojo queda reservado a danger.

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface AlertBannerProps {
  variant: "ok" | "warn" | "danger";
  children: ReactNode;
  className?: string;
}

const ESTILO: Record<AlertBannerProps["variant"], string> = {
  ok: "border-positivo/30 bg-positivo/5 text-positivo",
  warn: "border-atencion/40 bg-atencion/10 text-atencion",
  danger: "border-critico/40 bg-critico/10 text-critico",
};

export function AlertBanner({
  variant,
  children,
  className,
}: AlertBannerProps) {
  return (
    <div
      role={variant === "danger" ? "alert" : "status"}
      className={cn(
        "rounded-lg border px-4 py-3 font-sans text-sm font-medium",
        ESTILO[variant],
        className,
      )}
    >
      {children}
    </div>
  );
}
