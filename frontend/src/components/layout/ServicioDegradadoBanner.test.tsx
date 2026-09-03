// Banner "servicio degradado" — reacciona a ApiError.kind
//
// Actualizado 2026-09-03 (incidente "todo en blanco"): antes este test
// CONGELABA el bug — afirmaba que `unauthorized` y `network` NO debían avisar.
// Eran justo los dos modos en los que el usuario se quedaba mirando pantallas
// vacías sin explicación. Ahora el único silencio legítimo es `client` (4xx de
// validación/RBAC): ese error lo explica la propia pantalla, no una barra global.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ServicioDegradadoBanner } from "@/components/layout/ServicioDegradadoBanner";
import { ApiError } from "@/lib/api";

function renderConCliente() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ServicioDegradadoBanner />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return qc;
}

async function forzarErrorEnQuery(qc: QueryClient, err: unknown, key = "test") {
  await act(async () => {
    await qc
      .fetchQuery({ queryKey: [key], queryFn: () => Promise.reject(err) })
      .catch(() => {});
  });
}

describe("ServicioDegradadoBanner", () => {
  it("por default está oculto — no interrumpe cuando todo funciona", () => {
    renderConCliente();
    expect(
      screen.queryByTestId("servicio-degradado-banner"),
    ).not.toBeInTheDocument();
  });

  it("aparece cuando una query falla con ApiError.kind='timeout'", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(0, "lento", "timeout"));
    const banner = await screen.findByTestId("servicio-degradado-banner");
    expect(banner.textContent).toMatch(/servidor está tardando/i);
  });

  it("aparece cuando una query falla con ApiError.kind='server'", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(500, "boom", "server"));
    const banner = await screen.findByTestId("servicio-degradado-banner");
    expect(banner.textContent).toMatch(/error interno/i);
  });

  it("avisa cuando la sesión se pierde (401) — antes callaba y la pantalla quedaba en blanco", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(401, "expired", "unauthorized"));
    const banner = await screen.findByTestId("servicio-degradado-banner");
    expect(banner.textContent).toMatch(/sesión venció/i);
    expect(
      screen.getByRole("button", { name: /volver a entrar/i }),
    ).toBeInTheDocument();
  });

  it("avisa cuando no hay conexión (network)", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(0, "offline", "network"));
    const banner = await screen.findByTestId("servicio-degradado-banner");
    expect(banner.textContent).toMatch(/no hay conexión/i);
  });

  it("NO aparece con errores de client (4xx no-401): los explica la pantalla", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(422, "malo", "client"));
    expect(
      screen.queryByTestId("servicio-degradado-banner"),
    ).not.toBeInTheDocument();
  });

  it("se queda visible mientras el problema persiste y solo se va cuando una query triunfa", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(0, "lento", "timeout"));
    await screen.findByTestId("servicio-degradado-banner");
    await act(async () => {
      await qc.fetchQuery({ queryKey: ["ok"], queryFn: async () => 1 });
    });
    expect(
      screen.queryByTestId("servicio-degradado-banner"),
    ).not.toBeInTheDocument();
  });
});
