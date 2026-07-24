// AppShell — marco del cockpit: sidebar fijo + lienzo de contenido.
// Escritorio: sidebar estático. Móvil: sidebar como panel deslizable con un
// botón de menú (piso de calidad: usable en pantallas pequeñas).

import { Menu, X } from "lucide-react";
import { type ReactNode, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { Sidebar } from "@/components/layout/Sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  const { rol, puede, cerrarSesion } = useAuth();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const cerrar = () => void cerrarSesion();

  return (
    <div className="flex h-screen overflow-hidden bg-surface-muted">
      {/* Sidebar de escritorio */}
      <div className="hidden md:flex">
        <Sidebar rol={rol} puede={puede} onCerrarSesion={cerrar} />
      </div>

      {/* Sidebar móvil (overlay) */}
      {menuAbierto && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Cerrar menú"
            className="absolute inset-0 bg-ink/30"
            onClick={() => setMenuAbierto(false)}
          />
          <div className="absolute inset-y-0 left-0">
            <Sidebar rol={rol} puede={puede} onCerrarSesion={cerrar} />
          </div>
        </div>
      )}

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Barra superior solo en móvil */}
        <div className="flex items-center gap-3 border-b border-hairline bg-surface px-4 py-3 md:hidden">
          <button
            type="button"
            aria-label="Abrir menú"
            onClick={() => setMenuAbierto((v) => !v)}
            className="rounded-md p-1 text-ink-soft hover:bg-surface-muted hover:text-ink"
          >
            {menuAbierto ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </button>
          <span className="font-display text-base font-bold tracking-tight text-ink">
            COMPAS
          </span>
        </div>

        <main className="flex-1 overflow-y-auto px-6 py-6 md:px-8 md:py-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
