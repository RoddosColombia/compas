// frontend/src/lib/api.test.ts
//
// F-04 (auditoría 2026-09-02): el cliente HTTP debe tener timeout y errores
// tipados. Antes: peticiones de 65s colgaban al usuario sin mensaje.
// Ahora: 15s de tope + `ApiError.kind` distingue timeout / network /
// unauthorized / server / client — el UI puede mostrar "servicio degradado"
// cuando toca en vez de un spinner eterno.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type ApiErrorKind, apiFetch, apiJson, setAccessToken } from "@/lib/api";

// Mock global de fetch. Cada test lo re-configura.
const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  setAccessToken(null);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

// ─── ApiError.kind: taxonomía honesta ────────────────────────────────────

describe("ApiError.kind (F-04)", () => {
  it("tiene un `kind` explícito que el UI puede usar para escoger el mensaje", () => {
    const kinds: ApiErrorKind[] = [
      "timeout",
      "network",
      "unauthorized",
      "server",
      "client",
    ];
    for (const k of kinds) {
      const e = new ApiError(500, "test", k);
      expect(e.kind).toBe(k);
    }
  });

  it("si no se pasa `kind`, se deriva del status (backward compat con call sites viejos)", () => {
    // Call sites viejos como `lib/cargas.ts` hacen `new ApiError(r.status, detail)`
    // sin el 3er arg — el kind se auto-deriva del status para no romperlos.
    expect(new ApiError(500, "boom").kind).toBe("server");
    expect(new ApiError(401, "expired").kind).toBe("unauthorized");
    expect(new ApiError(422, "malo").kind).toBe("client");
    // Explícito gana sobre auto-derivación.
    expect(new ApiError(500, "boom", "timeout").kind).toBe("timeout");
  });
});

// ─── apiFetch: timeout de 15s ────────────────────────────────────────────

describe("apiFetch · timeout (F-04)", () => {
  it("aborta el fetch tras 15s y lanza ApiError con kind='timeout'", async () => {
    // fetch nunca resuelve, pero rechaza cuando el AbortController dispara.
    // Usamos `catch(() => {})` en la promesa del mock para que la rejection
    // interna no quede unhandled (el apiFetch la atrapa y la convierte a
    // ApiError; el mock solo la usa para saber que abort corrió).
    fetchMock.mockImplementation((_url, init: RequestInit) => {
      return new Promise((_, reject) => {
        init.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      });
    });

    vi.useFakeTimers();
    const p = apiFetch("/lento").catch((e) => e);
    await vi.advanceTimersByTimeAsync(16000);
    const err = await p;
    expect(err).toMatchObject({ kind: "timeout", status: 0 });
    vi.useRealTimers();
  });

  it("errores de red (fetch rechaza sin AbortError) → kind='network'", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(apiFetch("/algo")).rejects.toMatchObject({
      kind: "network",
    });
  });
});

// ─── apiJson: taxonomía de status codes ──────────────────────────────────

describe("apiJson · errores tipados por status (F-04)", () => {
  it("5xx → ApiError.kind='server'", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
    );
    await expect(apiJson("/x")).rejects.toMatchObject({
      kind: "server",
      status: 500,
    });
  });

  it("401 sin refresh → ApiError.kind='unauthorized'", async () => {
    // Sin cookie de refresh: /auth/refresh responde 401.
    fetchMock
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(new Response("{}", { status: 401 }));
    await expect(apiJson("/x")).rejects.toMatchObject({
      kind: "unauthorized",
      status: 401,
    });
  });

  it("4xx (no-401) → ApiError.kind='client'", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "malo" }), { status: 422 }),
    );
    await expect(apiJson("/x")).rejects.toMatchObject({
      kind: "client",
      status: 422,
    });
  });
});
