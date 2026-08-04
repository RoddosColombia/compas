// frontend/src/App.tsx — shell de la app: providers + router + cockpit.
//
// El cockpit (AppShell) monta el sidebar del Blueprint, cuyo árbol se deriva de
// las capacidades del rol (regla 9: prohibido mapear rol→ítems disperso; la
// fuente única es src/lib/navegacion.ts).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "@/auth/AuthContext";
import { AppShell } from "@/components/layout/AppShell";
import CabinaMesPage from "@/pages/CabinaMesPage";
import CajaPage from "@/pages/CajaPage";
import CargasPage from "@/pages/CargasPage";
import CategoriasPage from "@/pages/CategoriasPage";
import ControlPage from "@/pages/ControlPage";
import DashboardsPage from "@/pages/DashboardsPage";
import DatosPage from "@/pages/DatosPage";
import FlujoDiarioPage from "@/pages/FlujoDiarioPage";
import GastosRecurrentesPage from "@/pages/GastosRecurrentesPage";
import InicioPage from "@/pages/InicioPage";
import IvaPage from "@/pages/IvaPage";
import LoginPage from "@/pages/LoginPage";
import MesesPage from "@/pages/MesesPage";
import MetasPage from "@/pages/MetasPage";
import PresupuestoMesPage from "@/pages/PresupuestoMesPage";
import ProyeccionPage from "@/pages/ProyeccionPage";
import ReglasPage from "@/pages/ReglasPage";
import ReportesPage from "@/pages/ReportesPage";
import ScenariosPage from "@/pages/ScenariosPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function Protegida({ children }: { children: ReactNode }) {
  const { cargando, despertando, autenticado } = useAuth();
  if (cargando) {
    return (
      <p className="p-8 font-sans text-sm text-ink-soft">
        {despertando
          ? "Despertando el servidor… (la primera carga tras un rato puede tardar ~1 min)"
          : "Cargando sesión…"}
      </p>
    );
  }
  return autenticado ? <>{children}</> : <Navigate to="/login" replace />;
}

/** Ruta del cockpit: protegida + montada dentro del AppShell. */
function Cockpit({ children }: { children: ReactNode }) {
  return (
    <Protegida>
      <AppShell>{children}</AppShell>
    </Protegida>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            {/* ── Las 8 vistas del Blueprint ── */}
            <Route
              path="/inicio"
              element={
                <Cockpit>
                  <InicioPage />
                </Cockpit>
              }
            />
            <Route
              path="/mes"
              element={
                <Cockpit>
                  <CabinaMesPage />
                </Cockpit>
              }
            />
            <Route
              path="/proyeccion"
              element={
                <Cockpit>
                  <ProyeccionPage />
                </Cockpit>
              }
            />
            <Route
              path="/escenarios"
              element={
                <Cockpit>
                  <ScenariosPage />
                </Cockpit>
              }
            />
            <Route
              path="/control"
              element={
                <Cockpit>
                  <ControlPage />
                </Cockpit>
              }
            />
            <Route
              path="/iva"
              element={
                <Cockpit>
                  <IvaPage />
                </Cockpit>
              }
            />
            <Route
              path="/metas"
              element={
                <Cockpit>
                  <MetasPage />
                </Cockpit>
              }
            />
            <Route
              path="/flujo-diario"
              element={
                <Cockpit>
                  <FlujoDiarioPage />
                </Cockpit>
              }
            />
            <Route
              path="/dashboards"
              element={
                <Cockpit>
                  <DashboardsPage />
                </Cockpit>
              }
            />
            <Route
              path="/reportes"
              element={
                <Cockpit>
                  <ReportesPage />
                </Cockpit>
              }
            />
            <Route
              path="/datos"
              element={
                <Cockpit>
                  <DatosPage />
                </Cockpit>
              }
            />

            <Route
              path="/gastos-recurrentes"
              element={
                <Cockpit>
                  <GastosRecurrentesPage />
                </Cockpit>
              }
            />

            {/* ── Herramientas de captura existentes (se reubican en Fase B) ── */}
            <Route
              path="/meses"
              element={
                <Cockpit>
                  <MesesPage />
                </Cockpit>
              }
            />
            <Route
              path="/meses/:mes/presupuesto"
              element={
                <Cockpit>
                  <PresupuestoMesPage />
                </Cockpit>
              }
            />
            <Route
              path="/cargas"
              element={
                <Cockpit>
                  <CargasPage />
                </Cockpit>
              }
            />
            <Route
              path="/caja"
              element={
                <Cockpit>
                  <CajaPage />
                </Cockpit>
              }
            />
            <Route
              path="/categorias"
              element={
                <Cockpit>
                  <CategoriasPage />
                </Cockpit>
              }
            />
            <Route
              path="/reglas"
              element={
                <Cockpit>
                  <ReglasPage />
                </Cockpit>
              }
            />

            <Route path="*" element={<Navigate to="/inicio" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
