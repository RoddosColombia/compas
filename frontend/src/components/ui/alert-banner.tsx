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
  ok: "border-green/30 bg-green/5 text-green",
  warn: "border-amber/40 bg-amber/10 text-amber",
  danger: "border-red/40 bg-red/10 text-red",
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
