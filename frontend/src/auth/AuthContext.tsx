// frontend/src/auth/AuthContext.tsx
//
// Estado de sesión: restaura al cargar (cookie de refresh → access en memoria)
// y expone las capacidades del rol (navbar/acciones derivadas de un único
// config de permisos del backend — regla 9: prohibido mapear rol→UI aquí).

import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import * as api from "@/lib/api";

interface AuthState {
  cargando: boolean;
  despertando: boolean;
  autenticado: boolean;
  rol: string | null;
  capacidades: string[];
  puede: (cap: string) => boolean;
  refrescarCapacidades: () => Promise<void>;
  cerrarSesion: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [cargando, setCargando] = useState(true);
  // `despertando`: cold-start de Render Free (>2.5s en el refresh de arranque)
  // → mensaje intencional en vez de un spinner que parece congelado.
  const [despertando, setDespertando] = useState(false);
  const [autenticado, setAutenticado] = useState(false);
  const [rol, setRol] = useState<string | null>(null);
  const [capacidades, setCapacidades] = useState<string[]>([]);

  const refrescarCapacidades = useCallback(async () => {
    const caps = await api.capabilities();
    setRol(caps.rol);
    setCapacidades(caps.capabilities);
    setAutenticado(true);
  }, []);

  useEffect(() => {
    const lento = setTimeout(() => setDespertando(true), 2500);
    (async () => {
      if (await api.restaurarSesion()) {
        try {
          await refrescarCapacidades();
        } catch {
          setAutenticado(false);
        }
      }
      clearTimeout(lento);
      setDespertando(false);
      setCargando(false);
    })();
    return () => clearTimeout(lento);
  }, [refrescarCapacidades]);

  const cerrarSesion = useCallback(async () => {
    await api.logout();
    setAutenticado(false);
    setRol(null);
    setCapacidades([]);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      cargando,
      despertando,
      autenticado,
      rol,
      capacidades,
      puede: (cap) => capacidades.includes(cap),
      refrescarCapacidades,
      cerrarSesion,
    }),
    [
      cargando,
      despertando,
      autenticado,
      rol,
      capacidades,
      refrescarCapacidades,
      cerrarSesion,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth fuera de <AuthProvider>");
  return v;
}
