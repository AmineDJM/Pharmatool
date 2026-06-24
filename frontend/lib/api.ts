// Thin client for the Pharmatool FastAPI backend.
// The base URL is injected at build time via NEXT_PUBLIC_API_URL (Render env var);
// falls back to localhost for local development.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export type Row = Record<string, any>;

async function getJSON<T = any>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} sur ${path}${text ? ` — ${text}` : ""}`);
  }
  return res.json();
}

async function postJSON<T = any>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json())?.detail ?? "";
    } catch {
      /* ignore */
    }
    throw new Error(detail || `API ${res.status} sur ${path}`);
  }
  return res.json();
}

export const api = {
  meta: () => getJSON("/api/meta"),
  overview: () => getJSON("/api/overview"),
  radarNew: (months: number, minUsd: number, maxComp: number) =>
    getJSON(`/api/radar/new-registrations?months=${months}&min_usd=${minUsd}&max_competitors=${maxComp}`),
  radarWhite: (minUsd: number) => getJSON(`/api/radar/white-spaces?min_usd=${minUsd}`),
  radarExpirations: (validity: number, horizon: number) =>
    getJSON(`/api/radar/expirations?validity=${validity}&horizon=${horizon}`),
  opportunities: (view: string, minUsd: number, limit: number) =>
    getJSON(`/api/opportunities?view=${view}&min_usd=${minUsd}&limit=${limit}`),
  pricingSuggest: (q: string) => getJSON(`/api/pricing/suggest?q=${encodeURIComponent(q)}`),
  pricing: (dci: string, dosage?: string, forme?: string) => {
    const p = new URLSearchParams({ dci });
    if (dosage) p.set("dosage", dosage);
    if (forme) p.set("forme", forme);
    return getJSON(`/api/pricing?${p.toString()}`);
  },
  assistant: (question: string) => postJSON("/api/assistant", { question }),
};
