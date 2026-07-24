// shadcn/ui Button (estilo base). Prueba que el pipeline cva + cn + Tailwind
// funciona; el resto de componentes se añaden con `npx shadcn add ...`.
import { type VariantProps, cva } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-sans text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        // cyan = acción primaria del cockpit (Cyber Cyan)
        cyan: "bg-cyan text-white hover:bg-cyan/90",
        // green = confirmar/positivo (Growth Green)
        green: "bg-green text-white hover:bg-green/90",
        default: "bg-ink text-white hover:bg-ink/90",
        outline:
          "border border-hairline bg-transparent text-ink hover:bg-surface-muted",
        ghost: "text-ink hover:bg-surface-muted",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3",
        lg: "h-10 px-6",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { buttonVariants };
