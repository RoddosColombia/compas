// F-04 · Banner "servicio degradado" — reacciona a ApiError.kind

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ServicioDegradadoBanner } from "@/components/layout/ServicioDegradadoBanner";
import { ApiError } from "@/lib/api";

function renderConCliente() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ServicioDegradadoBanner />
    </QueryClientProvider>,
  );
  return qc;
}

async function forzarErrorEnQuery(qc: QueryClient, err: unknown) {
  // Ensucia una query con un error específico y notifica la cache.
  await act(async () => {
    await qc
      .fetchQuery({
        queryKey: ["test"],
        queryFn: () => Promise.reject(err),
      })
      .catch(() => {});
  });
}

describe("ServicioDegradadoBanner (F-04)", () => {
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
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toMatch(/servidor está tardando/i);
  });

  it("aparece cuando una query falla con ApiError.kind='server'", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(500, "boom", "server"));
    const banner = await screen.findByTestId("servicio-degradado-banner");
    expect(banner.textContent).toMatch(/error interno/i);
  });

  it("NO aparece con errores de client (4xx no-401), unauthorized o network", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(422, "malo", "client"));
    await forzarErrorEnQuery(qc, new ApiError(401, "expired", "unauthorized"));
    await forzarErrorEnQuery(qc, new ApiError(0, "offline", "network"));
    expect(
      screen.queryByTestId("servicio-degradado-banner"),
    ).not.toBeInTheDocument();
  });

  it("expone un botón Reintentar accesible por rol", async () => {
    const qc = renderConCliente();
    await forzarErrorEnQuery(qc, new ApiError(0, "lento", "timeout"));
    await screen.findByTestId("servicio-degradado-banner");
    expect(
      screen.getByRole("button", { name: /reintentar/i }),
    ).toBeInTheDocument();
  });
});
