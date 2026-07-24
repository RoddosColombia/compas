// Sidebar — navegación fija del cockpit (Blueprint §2).
// Marca RODDOS arriba, árbol de 3 grupos derivado de capacidades (regla 9),
// ítem activo = barra cian + fondo tenue, pie con rol + salir.
// Recibe `puede`/`rol`/`onCerrarSesion` por props (inyección) para ser testeable
// sin montar AuthContext; el AppShell los cablea desde useAuth.

import { NavLink } from "react-router-dom";

import { NAVEGACION } from "@/lib/navegacion";
import { cn } from "@/lib/utils";

interface SidebarProps {
  rol: string | null;
  puede: (cap: string) => boolean;
  onCerrarSesion: () => void;
}

export function Sidebar({ rol, puede, onCerrarSesion }: SidebarProps) {
  const grupos = NAVEGACION.map((g) => ({
    ...g,
    items: g.items.filter((i) => puede(i.cap)),
  })).filter((g) => g.items.length > 0);

  return (
    <aside className="flex h-full w-60 flex-col border-r border-hairline bg-surface">
      {/* Marca */}
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan font-display text-sm font-bold text-white">
          C
        </span>
        <div className="leading-none">
          <p className="font-display text-base font-bold tracking-tight text-ink">
            COMPAS
          </p>
          <p className="mt-0.5 font-sans text-[10px] font-medium tracking-wide text-ink-faint uppercase">
            RODDOS
          </p>
        </div>
      </div>

      {/* Árbol */}
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {grupos.map((grupo) => (
          <div key={grupo.titulo} className="mb-5">
            <p className="px-3 pb-1.5 font-sans text-[10px] font-semibold tracking-wider text-ink-faint uppercase">
              {grupo.titulo}
            </p>
            <ul className="space-y-0.5">
              {grupo.items.map((item) => {
                const Icono = item.icon;
                return (
                  <li key={item.path}>
                    <NavLink
                      to={item.path}
                      className={({ isActive }) =>
                        cn(
                          "relative flex items-center gap-2.5 rounded-lg px-3 py-2 font-sans text-sm transition-colors",
                          isActive
                            ? "bg-cyan-tint font-semibold text-ink"
                            : "font-medium text-ink-soft hover:bg-surface-muted hover:text-ink",
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && (
                            <span className="absolute top-1.5 bottom-1.5 -left-3 w-1 rounded-r bg-cyan" />
                          )}
                          <Icono className="h-4 w-4 shrink-0" />
                          {item.label}
                        </>
                      )}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Pie: rol + salir */}
      <div className="border-t border-hairline px-4 py-3">
        <div className="flex items-center justify-between">
          <span className="font-sans text-xs text-ink-soft capitalize">
            {rol}
          </span>
          <button
            type="button"
            onClick={onCerrarSesion}
            className="rounded-md px-2 py-1 font-sans text-xs font-medium text-ink-soft transition-colors hover:bg-surface-muted hover:text-ink"
          >
            Salir
          </button>
        </div>
      </div>
    </aside>
  );
}
