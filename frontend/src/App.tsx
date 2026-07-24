// frontend/src/App.tsx — shell de la app: providers + router + layout.
//
// El navbar se deriva de las capacidades del rol (GET /auth/capabilities) —
// regla 9: prohibido mapear rol→ítems en el frontend.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import CajaPage from "@/pages/CajaPage";
import CargasPage from "@/pages/CargasPage";
import CategoriasPage from "@/pages/CategoriasPage";
import ControlPage from "@/pages/ControlPage";
import LoginPage from "@/pages/LoginPage";
import MesesPage from "@/pages/MesesPage";
import ProyeccionPage from "@/pages/ProyeccionPage";
import ReglasPage from "@/pages/ReglasPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function Protegida({ children }: { children: ReactNode }) {
  const { cargando, despertando, autenticado } = useAuth();
  if (cargando) {
    return (
      <p className="p-8 text-sm text-slate-500">
        {despertando
          ? "Despertando el servidor… (la primera carga tras un rato puede tardar ~1 min)"
          : "Cargando sesión…"}
      </p>
    );
  }
  return autenticado ? <>{children}</> : <Navigate to="/login" replace />;
}

function Layout({ children }: { children: ReactNode }) {
  const { rol, puede, cerrarSesion } = useAuth();
  return (
    <div className="mx-auto min-h-screen max-w-5xl p-6">
      <nav className="mb-8 flex items-center justify-between border-b border-slate-200 pb-4">
        <div className="flex items-center gap-6">
          <h1 className="text-lg font-bold tracking-tight">COMPAS</h1>
          {puede("dashboard:leer") && (
            <Link
              to="/meses"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Meses
            </Link>
          )}
          {puede("dashboard:leer") && (
            <Link
              to="/proyeccion"
              className="text-sm font-medium text-brand hover:text-brand/80"
            >
              Proyecciones
            </Link>
          )}
          {puede("dashboard:leer") && (
            <Link
              to="/control"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Control
            </Link>
          )}
          {puede("caja:reportar") && (
            <Link
              to="/caja"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Caja
            </Link>
          )}
          {puede("cargas:gestionar") && (
            <Link
              to="/cargas"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Cargas
            </Link>
          )}
          {puede("dashboard:leer") && (
            <Link
              to="/categorias"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Categorías
            </Link>
          )}
          {puede("dashboard:leer") && (
            <Link
              to="/reglas"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Reglas
            </Link>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 capitalize">{rol}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void cerrarSesion()}
          >
            Salir
          </Button>
        </div>
      </nav>
      {children}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/meses"
              element={
                <Protegida>
                  <Layout>
                    <MesesPage />
                  </Layout>
                </Protegida>
              }
            />
            <Route
              path="/cargas"
              element={
                <Protegida>
                  <Layout>
                    <CargasPage />
                  </Layout>
                </Protegida>
              }
            />
            <Route
              path="/proyeccion"
              element={
                <Protegida>
                  <Layout>
                    <ProyeccionPage />
                  </Layout>
                </Protegida>
              }
            />
            <Route
              path="/control"
              element={
                <Protegida>
                  <Layout>
                    <ControlPage />
                  </Layout>
                </Protegida>
              }
            />
            <Route
              path="/caja"
              element={
                <Protegida>
                  <Layout>
                    <CajaPage />
                  </Layout>
                </Protegida>
              }
            />
            <Route
              path="/categorias"
              element={
                <Protegida>
                  <Layout>
                    <CategoriasPage />
                  </Layout>
                </Protegida>
              }
            />
            <Route
              path="/reglas"
              element={
                <Protegida>
                  <Layout>
                    <ReglasPage />
                  </Layout>
                </Protegida>
              }
            />
            <Route path="*" element={<Navigate to="/meses" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
