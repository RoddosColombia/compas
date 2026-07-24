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
import CajaPage from "@/pages/CajaPage";
import CargasPage from "@/pages/CargasPage";
import CategoriasPage from "@/pages/CategoriasPage";
import ControlPage from "@/pages/ControlPage";
import EnConstruccion from "@/pages/EnConstruccion";
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

// Herramientas de captura que ya existen; se agrupan bajo "Datos" mientras la
// vista definitiva de la Fase B las absorbe.
const ENLACES_DATOS = [
  { label: "Caja", path: "/caja" },
  { label: "Cargas", path: "/cargas" },
  { label: "Categorías", path: "/categorias" },
  { label: "Reglas", path: "/reglas" },
  { label: "Meses", path: "/meses" },
];

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
                  <EnConstruccion
                    vista="Inicio"
                    descripcion="Pulso ejecutivo: caja, runway y alertas del mes."
                  />
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
                  <EnConstruccion
                    vista="Escenarios"
                    descripcion="Comparar pesimista, base y optimista superpuestos."
                  />
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
                  <EnConstruccion
                    vista="IVA"
                    descripcion="Generado, descontable y liquidación cuatrimestral."
                  />
                </Cockpit>
              }
            />
            <Route
              path="/dashboards"
              element={
                <Cockpit>
                  <EnConstruccion
                    vista="Dashboards"
                    descripcion="Cartera, mora, cobranza y colocación."
                  />
                </Cockpit>
              }
            />
            <Route
              path="/reportes"
              element={
                <Cockpit>
                  <EnConstruccion
                    vista="Reportes"
                    descripcion="Actualizaciones para el board y export a PDF."
                  />
                </Cockpit>
              }
            />
            <Route
              path="/datos"
              element={
                <Cockpit>
                  <EnConstruccion
                    vista="Datos"
                    descripcion="Caja inicial y captura de supuestos y presupuestos."
                    enlaces={ENLACES_DATOS}
                  />
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
