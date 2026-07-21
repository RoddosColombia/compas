// frontend/src/lib/api.ts
//
// Cliente API de COMPAS. Reglas de CLAUDE.md:
//   • Access token SOLO en memoria (nunca localStorage); el refresh vive en una
//     cookie HttpOnly que el navegador envía con credentials:'include'.
//   • En 401 se intenta UN refresh (single-flight: N peticiones concurrentes
//     comparten el mismo POST /auth/refresh) y se reintenta la petición.
//   • Los montos viajan como string; este módulo no los toca.

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

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

// Timeout del refresh de arranque: en Render Free un cold-start puede tardar
// ~50s; sin tope, el spinner de "Cargando sesión…" se ve congelado. Con 15s el
// arranque cae al login en vez de colgarse, y el reintento del usuario ya
// encuentra el server despierto.
const REFRESH_TIMEOUT_MS = 15000;

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
      if (!r.ok) return false;
      const data = (await r.json()) as { access_token: string };
      accessToken = data.access_token;
      return true;
    } catch {
      return false; // 401, red caída, o timeout (cold-start) → sin sesión
    } finally {
      clearTimeout(t);
      refreshEnCurso = null;
    }
  })();
  return refreshEnCurso;
}

/** fetch autenticado contra /api/v1; reintenta UNA vez tras refresh en 401. */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
  reintentar = true,
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
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
    throw new ApiError(r.status, detail);
  }
  return body as T;
}

// ── Auth ──────────────────────────────────────────────────────────────

export type LoginResultado = { tipo: "ok" } | { tipo: "mfa"; mfaToken: string };

export async function login(
  email: string,
  password: string,
): Promise<LoginResultado> {
  const r = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok)
    throw new ApiError(r.status, body.detail ?? "Error de autenticación");
  if (body.mfa_required) return { tipo: "mfa", mfaToken: body.mfa_token };
  accessToken = body.access_token;
  return { tipo: "ok" };
}

export async function mfaVerify(mfaToken: string, code: string): Promise<void> {
  const r = await fetch(`${API}/auth/mfa/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ mfa_token: mfaToken, code }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, body.detail ?? "Código inválido");
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
