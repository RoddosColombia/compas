// frontend/src/pages/LoginPage.tsx — login con paso MFA (challenge → verify).

import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import * as api from "@/lib/api";

export default function LoginPage() {
  const nav = useNavigate();
  const { refrescarCapacidades } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function alEntrar() {
    await refrescarCapacidades();
    nav("/inicio", { replace: true });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      if (mfaToken) {
        await api.mfaVerify(mfaToken, code);
        await alEntrar();
        return;
      }
      const r = await api.login(email, password);
      if (r.tipo === "mfa") {
        setMfaToken(r.mfaToken);
      } else {
        await alEntrar();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error inesperado");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">COMPAS</h1>
        <p className="text-sm text-slate-500">
          Control presupuestal — RODDOS S.A.S.
        </p>
      </div>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        {mfaToken === null ? (
          <>
            <label className="text-sm font-medium" htmlFor="email">
              Correo
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="username"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <label className="text-sm font-medium" htmlFor="password">
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </>
        ) : (
          <>
            <label className="text-sm font-medium" htmlFor="code">
              Código de tu app de autenticación
            </label>
            <input
              id="code"
              inputMode="numeric"
              required
              autoComplete="one-time-code"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </>
        )}
        {error && <p className="text-sm text-critico-600">{error}</p>}
        <Button type="submit" disabled={enviando}>
          {enviando ? "Entrando…" : mfaToken ? "Verificar" : "Entrar"}
        </Button>
      </form>
    </main>
  );
}
