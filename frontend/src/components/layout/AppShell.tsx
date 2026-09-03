// AppShell — marco del cockpit: sidebar fijo + lienzo de contenido.
// Escritorio: sidebar estático. Móvil: sidebar como panel deslizable con un
// botón de menú (piso de calidad: usable en pantallas pequeñas).

import { Menu, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useLocation } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { FabsPanel } from "@/components/fabs/FabsPanel";
import { MesStatusBar } from "@/components/layout/MesStatusBar";
import { ServicioDegradadoBanner } from "@/components/layout/ServicioDegradadoBanner";
import { Sidebar } from "@/components/layout/Sidebar";

// FIX-UI-1: Proyecciones es la vista-cockpit del CEO (tabla ancha + gráfica) y debe
// caber como una foto sin scroll lateral a su resolución (~1918px). Ahí el lienzo usa
// el ancho completo del viewport; el resto del cockpit sigue centrado a max-w-6xl para
// no volver ilegibles las vistas de formulario. El sticky del header/1ª columna vive en
// TablaEgreso, no aquí.
export function anchoContenido(pathname: string): string {
  return pathname.startsWith("/proyeccion") ? "w-full" : "mx-auto max-w-6xl";
}

export function AppShell({ children }: { children: ReactNode }) {
  const { rol, puede, cerrarSesion } = useAuth();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [fabsAbierto, setFabsAbierto] = useState(false);
  const cerrar = () => void cerrarSesion();
  const { pathname } = useLocation();

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

        {/* F-04 (auditoría 2026-09-02): banner de servicio degradado — se
            muestra automáticamente cuando una query falla con ApiError.kind
            timeout|server; oculto por default. Va ANTES del MesStatusBar para
            que un backend caído no oculte la señal más urgente. */}
        <ServicioDegradadoBanner />

        {/* Barra de estado del mes (C2): visible en todas las rutas del cockpit */}
        <MesStatusBar />

        <main className="flex-1 overflow-y-auto px-6 py-6 md:px-8 md:py-8">
          <div className={anchoContenido(pathname)}>{children}</div>
        </main>
      </div>

      {puede("cfo:consultar") && (
        <>
          <button
            type="button"
            onClick={() => setFabsAbierto(true)}
            className="fixed right-4 bottom-4 z-40 rounded-full bg-cyan px-4 py-2 font-sans text-sm font-medium text-white shadow-lg"
          >
            Preguntá a FABS
          </button>
          {fabsAbierto && <FabsPanel onCerrar={() => setFabsAbierto(false)} />}
        </>
      )}
    </div>
  );
}
