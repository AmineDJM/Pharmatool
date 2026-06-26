// Thin client for the Pharmatool FastAPI backend.
// The base URL is injected at build time via NEXT_PUBLIC_API_URL (Render env var);
// falls back to localhost for local development.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export type Row = Record<string, any>;

/* ---------- Shared-password auth ---------- */
const PW_KEY = "pt_pw";

export function getPw(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(PW_KEY) || "";
}
export function setPw(pw: string) {
  if (typeof window !== "undefined") localStorage.setItem(PW_KEY, pw);
}
export function clearPw() {
  if (typeof window !== "undefined") localStorage.removeItem(PW_KEY);
}
function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) };
  const pw = getPw();
  if (pw) h["x-app-password"] = pw;
  return h;
}
function onUnauthorized() {
  clearPw();
  if (typeof window !== "undefined") window.dispatchEvent(new Event("pt-unauth"));
}

async function getJSON<T = any>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", headers: authHeaders() });
  if (res.status === 401) {
    onUnauthorized();
    throw new Error("Session expirée — reconnecte-toi.");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} sur ${path}${text ? ` — ${text}` : ""}`);
  }
  return res.json();
}

async function postJSON<T = any>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (res.status === 401) {
    if (!path.includes("/login")) onUnauthorized();
    let d = "";
    try {
      d = (await res.json())?.detail ?? "";
    } catch {
      /* ignore */
    }
    throw new Error(d || "unauthorized");
  }
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

export type DciParams = {
  dci: string[];
  markets?: string[];
  dosage?: string[];
  forme?: string[];
  lab?: string[];
  statut?: string[];
};

// Build a query string, appending one entry per value for array params
// (?dci=a&dci=b) so values containing commas (lab names) survive intact.
function buildQuery(params: Record<string, string | string[] | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) v.forEach((x) => x !== null && x !== undefined && x !== "" && sp.append(k, String(x)));
    else if (v !== "") sp.append(k, String(v));
  }
  return sp.toString();
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
  dciOptions: (q: string) => getJSON(`/api/dci/options?q=${encodeURIComponent(q)}`),
  dciFacets: (p: DciParams) => getJSON(`/api/dci/facets?${buildQuery({ ...p })}`),
  dciAnalysis: (p: DciParams) => getJSON(`/api/dci/analysis?${buildQuery({ ...p })}`),
  pricing: (p: DciParams) => getJSON(`/api/pricing?${buildQuery({ ...p })}`),
  assistant: (question: string) => postJSON("/api/assistant", { question }),
  login: (password: string) => postJSON("/api/login", { password }),
};
