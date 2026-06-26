"use client";

import { useEffect, useState } from "react";
import { api, getPw, setPw, clearPw } from "@/lib/api";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [pw, setPwInput] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setAuthed(!!getPw());
    const onUnauth = () => setAuthed(false);
    window.addEventListener("pt-unauth", onUnauth);
    return () => window.removeEventListener("pt-unauth", onUnauth);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!pw.trim()) return;
    setBusy(true);
    setErr("");
    try {
      await api.login(pw.trim());
      setPw(pw.trim());
      setPwInput("");
      setAuthed(true);
    } catch {
      clearPw();
      setErr("Mot de passe incorrect.");
    } finally {
      setBusy(false);
    }
  }

  if (authed === null) return null; // initial check — avoid flashing the login screen
  if (authed) return <>{children}</>;

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-5">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-white p-7 shadow-2xl">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-accent text-2xl">💊</span>
          <div className="leading-tight">
            <div className="text-lg font-bold text-ink">Pharma Intelligence</div>
            <div className="text-xs text-slate-500">Accès réservé</div>
          </div>
        </div>

        <label className="mb-1 block text-sm font-medium text-slate-600">Mot de passe</label>
        <input
          autoFocus
          type="password"
          inputMode="numeric"
          value={pw}
          onChange={(e) => setPwInput(e.target.value)}
          placeholder="••••••••"
          className="input text-center text-lg tracking-widest"
        />
        {err && <p className="mt-2 text-sm text-rose-600">{err}</p>}

        <button type="submit" disabled={busy} className="btn-primary mt-5 w-full py-3 text-base">
          {busy ? "Vérification…" : "Entrer"}
        </button>
      </form>
    </div>
  );
}

export function LogoutButton({ className = "" }: { className?: string }) {
  return (
    <button
      onClick={() => {
        clearPw();
        window.dispatchEvent(new Event("pt-unauth"));
      }}
      className={className}
    >
      Déconnexion
    </button>
  );
}
