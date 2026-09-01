// Sidebar — navegación fija del cockpit (Blueprint §2).
// Marca RODDOS arriba, árbol de grupos derivado de capacidades (regla 9),
// ítem activo = barra cian + fondo tenue, pie con rol + salir.
// Recibe `puede`/`rol`/`onCerrarSesion` por props (inyección) para ser testeable
// sin montar AuthContext; el AppShell los cablea desde useAuth.
//
// RV-V6/V7 · Fase B del navegador (2026-09-01): un item con `subItems` se
// pinta como grupo COLAPSABLE. Se auto-expande cuando la ruta actual matchea
// un sub-path. El clic en el header alterna abierto/cerrado. El sidebar top-
// level pasó de 19 a 11 entradas (colapsó el mes y los catálogos).

import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { type ItemNav, NAVEGACION } from "@/lib/navegacion";
import { cn } from "@/lib/utils";

interface SidebarProps {
  rol: string | null;
  puede: (cap: string) => boolean;
  onCerrarSesion: () => void;
}

/** ¿El path actual matchea `item.path` o alguno de sus subItems? */
function esActivo(item: ItemNav, pathname: string): boolean {
  if (pathname === item.path) return true;
  for (const s of item.subItems ?? []) {
    if (pathname === s.path || pathname.startsWith(`${s.path}/`)) return true;
  }
  return false;
}

/** Filtra un item (y sus subItems) por permisos. Devuelve null si el propio
 * item no tiene permiso o si tras filtrar subItems queda un grupo vacío. */
function filtrarItem(
  item: ItemNav,
  puede: (cap: string) => boolean,
): ItemNav | null {
  if (!puede(item.cap)) return null;
  if (!item.subItems) return item;
  const subItems = item.subItems.filter((s) => puede(s.cap));
  if (subItems.length === 0) return null;
  return { ...item, subItems };
}

export function Sidebar({ rol, puede, onCerrarSesion }: SidebarProps) {
  const location = useLocation();
  const grupos = useMemo(
    () =>
      NAVEGACION.map((g) => ({
        ...g,
        items: g.items
          .map((i) => filtrarItem(i, puede))
          .filter((i): i is ItemNav => i !== null),
      })).filter((g) => g.items.length > 0),
    [puede],
  );

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
          <p className="mt-0.5 font-sans text-apoyo font-medium tracking-wide text-ink-faint uppercase">
            RODDOS
          </p>
        </div>
      </div>

      {/* Árbol */}
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {grupos.map((grupo) => (
          <div key={grupo.titulo} className="mb-5">
            <p className="px-3 pb-1.5 font-sans text-apoyo font-semibold tracking-wider text-ink-faint uppercase">
              {grupo.titulo}
            </p>
            <ul className="space-y-0.5">
              {grupo.items.map((item) =>
                item.subItems ? (
                  <GrupoColapsable
                    key={item.path}
                    item={item}
                    pathname={location.pathname}
                  />
                ) : (
                  <ItemHoja key={item.path} item={item} />
                ),
              )}
            </ul>
          </div>
        ))}
      </nav>

      {/* Pie: rol + salir */}
      <div className="border-t border-hairline px-4 py-3">
        <div className="flex items-center justify-between">
          <span className="font-sans text-apoyo text-ink-soft capitalize">
            {rol}
          </span>
          <button
            type="button"
            onClick={onCerrarSesion}
            className="rounded-md px-2 py-1 font-sans text-apoyo font-medium text-ink-soft transition-colors hover:bg-surface-muted hover:text-ink"
          >
            Salir
          </button>
        </div>
      </div>
    </aside>
  );
}

// ─── Ítem hoja (link simple) ────────────────────────────────────────────────

function ItemHoja({ item }: { item: ItemNav }) {
  const Icono = item.icon;
  return (
    <li>
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
}

// ─── Grupo colapsable (item con subItems) ──────────────────────────────────

function GrupoColapsable({
  item,
  pathname,
}: {
  item: ItemNav;
  pathname: string;
}) {
  const Icono = item.icon;
  // Auto-expandir si la ruta actual matchea un sub-path.
  const autoExpandido = esActivo(item, pathname);
  const [manualAbierto, setManualAbierto] = useState<boolean | null>(null);
  const abierto = manualAbierto ?? autoExpandido;

  return (
    <li>
      <button
        type="button"
        onClick={() => setManualAbierto(!abierto)}
        aria-expanded={abierto}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 font-sans text-sm transition-colors",
          autoExpandido
            ? "font-semibold text-ink"
            : "font-medium text-ink-soft hover:bg-surface-muted hover:text-ink",
        )}
      >
        <Icono className="h-4 w-4 shrink-0" />
        <span className="flex-1 text-left">{item.label}</span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-ink-faint transition-transform",
            abierto && "rotate-180",
          )}
        />
      </button>
      {abierto && (
        <ul className="mt-0.5 ml-4 space-y-0.5 border-l border-hairline pl-2">
          {(item.subItems ?? []).map((sub) => (
            <ItemHoja key={sub.path} item={sub} />
          ))}
        </ul>
      )}
    </li>
  );
}
