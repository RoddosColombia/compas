// frontend/src/lib/api.ts
//
// Cliente API de COMPAS. Reglas de CLAUDE.md:
//   • Access token SOLO en memoria (nunca localStorage); el refresh vive en una
//     cookie HttpOnly que el navegador envía con credentials:'include'.
//   • En 401 se intenta UN refresh (single-flight: N peticiones concurrentes
//     comparten el mismo POST /auth/refresh) y se reintenta la petición.
//   • Los montos viajan como string; este módulo no los toca.
//
// F-04 (auditoría 2026-09-02): el cliente HTTP ahora tiene TIMEOUT de 15s y
// errores TIPADOS. Antes un backend degradado colgaba al usuario con un spinner
// eterno; ahora la petición aborta a los 15s y `ApiError.kind` distingue
// timeout / network / unauthorized / server / client — el UI puede mostrar
// mensajes honestos y un banner de "servicio degradado" cuando toca.

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const API = `${BASE}/api/v1`;

let accessToken: string | null = null;
let refreshEnCurso: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function haySesion(): boolean {
  return accessToken !== null;
}

// ─── Errores tipados (F-04) ────────────────────────────────────────────────
//
// El UI escoge el mensaje por `kind`, no por status. `status=0` significa
// "no hubo respuesta" (timeout o red caída) — el backend nunca lo envía.

export type ApiErrorKind =
  | "timeout"      // AbortController disparó — servidor tardó > 15s
  | "network"     // fetch rechazó sin abort (DNS, CORS bloqueado, offline)
  | "unauthorized" // 401 sin refresh viable — sesión perdida
  | "server"      // 5xx — backend degradado / mongo caído / bug
  | "client";     // 4xx (no-401) — validación / RBAC / recurso inexistente

export class ApiError extends Error {
  status: number;
  kind: ApiErrorKind;
  constructor(status: number, detail: string, kind?: ApiErrorKind) {
    super(detail);
    this.status = status;
    // Si el call site no pasa `kind`, lo derivamos del status (mismo mapeo
    // que usa `kindDeStatus` para respuestas HTTP). Los call sites viejos
    // en `lib/cargas.ts`, `lib/facturas.ts`, etc. quedan compatibles sin
    // tocarlos — el `kind` se les asigna correctamente por el status.
    this.kind = kind ?? kindDeStatus(status);
  }
}

// Timeout de cada petición autenticada. En Render Free un cold-start puede
// tardar ~50s; con 15s el usuario ve el error rápido y reintenta cuando el
// server ya despertó, en vez de esperar un minuto de spinner.
const REQUEST_TIMEOUT_MS = 15000;
const REFRESH_TIMEOUT_MS = 15000;

/** Clasifica cualquier excepción de `fetch` en un `ApiError` tipado. */
function excepcionAApiError(e: unknown): ApiError {
  // AbortError puede venir como DOMException o como TimeoutError (según runtime).
  if (
    e instanceof DOMException &&
    (e.name === "AbortError" || e.name === "TimeoutError")
  ) {
    return new ApiError(0, "La petición tardó demasiado (más de 15 s).", "timeout");
  }
  const msg = e instanceof Error ? e.message : String(e);
  return new ApiError(0, `Sin conexión con el servidor: ${msg}`, "network");
}

/** Traduce status HTTP a `ApiErrorKind` (después de descartar timeout/network). */
function kindDeStatus(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status >= 500) return "server";
  return "client";
}

// ─── refresh (single-flight) ──────────────────────────────────────────────

async function refrescar(): Promise<boolean> {
  refreshEnCurso ??= (async () => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), REFRESH_TIMEOUT_MS);
    try {
      const r = await fetch(`${API}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        signal: ctrl.signal,
      });
      if (!r.ok) {
        // F-05 (auditoría 2026-09-02): limpiar el token cuando refresh falla.
        // Antes: el token viejo quedaba en memoria → la próxima petición lo
        // enviaba, otro 401, otro refresh que fallaba igual, loop. Ahora la
        // próxima llamada a apiFetch no envía Authorization y el UI puede
        // detectar `haySesion() === false` para redirigir a /login limpio.
        accessToken = null;
        return false;
      }
      const data = (await r.json()) as { access_token: string };
      accessToken = data.access_token;
      return true;
    } catch {
      // Timeout, red caída o body no-json — misma consecuencia: sesión perdida.
      accessToken = null;
      return false;
    } finally {
      clearTimeout(t);
      refreshEnCurso = null;
    }
  })();
  return refreshEnCurso;
}

// ─── apiFetch: fetch autenticado con timeout duro ─────────────────────────

/** fetch autenticado contra /api/v1 con timeout de 15s; reintenta UNA vez
 *  tras refresh en 401. Errores de red/timeout viajan como ApiError tipado
 *  (no como TypeError sin diagnóstico). */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
  reintentar = true,
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  let r: Response;
  try {
    r = await fetch(`${API}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: init.signal ?? ctrl.signal,
    });
  } catch (e) {
    throw excepcionAApiError(e);
  } finally {
    clearTimeout(t);
  }
  if (r.status === 401 && reintentar && (await refrescar())) {
    return apiFetch(path, init, false);
  }
  return r;
}

/** apiFetch + parseo JSON + error tipado con el `detail` del backend. */
export async function apiJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const r = await apiFetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail ?? body);
    throw new ApiError(r.status, detail, kindDeStatus(r.status));
  }
  return body as T;
}

// ── Auth ──────────────────────────────────────────────────────────────

export type LoginResultado = { tipo: "ok" } | { tipo: "mfa"; mfaToken: string };

export async function login(
  email: string,
  password: string,
): Promise<LoginResultado> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  let r: Response;
  try {
    r = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
      signal: ctrl.signal,
    });
  } catch (e) {
    throw excepcionAApiError(e);
  } finally {
    clearTimeout(t);
  }
  const body = await r.json().catch(() => ({}));
  if (!r.ok)
    throw new ApiError(
      r.status,
      body.detail ?? "Error de autenticación",
      kindDeStatus(r.status),
    );
  if (body.mfa_required) return { tipo: "mfa", mfaToken: body.mfa_token };
  accessToken = body.access_token;
  return { tipo: "ok" };
}

export async function mfaVerify(mfaToken: string, code: string): Promise<void> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  let r: Response;
  try {
    r = await fetch(`${API}/auth/mfa/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ mfa_token: mfaToken, code }),
      signal: ctrl.signal,
    });
  } catch (e) {
    throw excepcionAApiError(e);
  } finally {
    clearTimeout(t);
  }
  const body = await r.json().catch(() => ({}));
  if (!r.ok)
    throw new ApiError(
      r.status,
      body.detail ?? "Código inválido",
      kindDeStatus(r.status),
    );
  accessToken = body.access_token;
}

export async function logout(): Promise<void> {
  try {
    await apiFetch("/auth/logout", { method: "POST" });
  } finally {
    accessToken = null;
  }
}

/** Intenta restaurar la sesión al cargar la app (cookie de refresh). */
export async function restaurarSesion(): Promise<boolean> {
  return refrescar();
}

export async function capabilities(): Promise<{
  rol: string;
  capabilities: string[];
}> {
  return apiJson("/auth/capabilities");
}
