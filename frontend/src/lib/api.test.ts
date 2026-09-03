// frontend/src/lib/api.test.ts
//
// F-04 (auditoría 2026-09-02): el cliente HTTP debe tener timeout y errores
// tipados. Antes: peticiones de 65s colgaban al usuario sin mensaje.
// Ahora: 15s de tope + `ApiError.kind` distingue timeout / network /
// unauthorized / server / client — el UI puede mostrar "servicio degradado"
// cuando toca en vez de un spinner eterno.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  type ApiErrorKind,
  apiFetch,
  apiJson,
  haySesion,
  restaurarSesion,
  setAccessToken,
} from "@/lib/api";

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

// ─── F-05: refresh single-flight + limpieza de sesión al fallar ───────────
//
// Auditor 2026-09-02 marcó F-05 pero: (a) el single-flight YA existe
// (`refreshEnCurso ??= ...`) — sólo lo blindamos con test; (b) el retry
// después de refresh fallido YA se cortocircuita con `&&` en apiFetch.
// GAP REAL: refresh fallido no limpiaba `accessToken` — la próxima petición
// mandaba el Bearer viejo, otro 401, otro refresh fallido, loop. FIX +
// tests que blindan el comportamiento correcto para siempre.

describe("refresh: single-flight + limpieza al fallar (F-05)", () => {
  it("single-flight — N llamadas concurrentes disparan UN solo POST /auth/refresh", async () => {
    setAccessToken("token-viejo");
    // 6 peticiones paralelas — todas reciben 401.
    fetchMock.mockImplementation(async (url) => {
      const u = String(url);
      if (u.endsWith("/auth/refresh")) {
        // Simula latencia leve para forzar concurrencia.
        await new Promise((r) => setTimeout(r, 5));
        return new Response(JSON.stringify({ access_token: "token-nuevo" }), {
          status: 200,
        });
      }
      return new Response("{}", { status: 401 });
    });

    const paralelo = Array.from({ length: 6 }, () => apiFetch("/x"));
    await Promise.allSettled(paralelo);

    const llamadasRefresh = fetchMock.mock.calls.filter((c) =>
      String(c[0]).endsWith("/auth/refresh"),
    );
    expect(llamadasRefresh).toHaveLength(1);
  });

  it("refresh fallido limpia accessToken — la próxima petición ya no envía el Bearer viejo", async () => {
    setAccessToken("token-expirado");
    expect(haySesion()).toBe(true);

    // /auth/refresh también responde 401 (cookie inválida, sesión perdida).
    // (sin parámetro `url`: no se usa, y con `noUnusedParameters` rompía
    // `tsc -b` -> `npm run build` fallaba y Vercel no publicaba NADA.)
    fetchMock.mockImplementation(async () => {
      return new Response("{}", { status: 401 });
    });

    // Llamamos restaurarSesion (patrón del arranque de la app). El refresh
    // interno falla; el token viejo DEBE quedar limpio.
    const ok = await restaurarSesion();
    expect(ok).toBe(false);
    expect(haySesion()).toBe(false); // ← el fix de F-05
  });

  it("apiFetch NO reintenta el fetch original si refresh falla", async () => {
    setAccessToken("token-viejo");
    // (sin parámetro `url`: no se usa, y con `noUnusedParameters` rompía
    // `tsc -b` -> `npm run build` fallaba y Vercel no publicaba NADA.)
    fetchMock.mockImplementation(async () => {
      return new Response("{}", { status: 401 });
    });

    await apiFetch("/x");

    // Debe haberse llamado: 1) /x (401) → 2) /auth/refresh (401). NO
    // una 3ª llamada a /x reintentada.
    const llamadasA_x = fetchMock.mock.calls.filter((c) =>
      String(c[0]).endsWith("/x"),
    );
    expect(llamadasA_x).toHaveLength(1);
  });
});
