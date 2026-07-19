import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Helper de shadcn/ui para componer clases de Tailwind. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
