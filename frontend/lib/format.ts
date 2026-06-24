// Display formatters — French locale, compact for big market values.

export function fmtMoney(v: number | null | undefined, currency = "DZD"): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  let s: string;
  if (abs >= 1e9) s = (v / 1e9).toFixed(2) + " Md";
  else if (abs >= 1e6) s = (v / 1e6).toFixed(1) + " M";
  else if (abs >= 1e3) s = (v / 1e3).toFixed(0) + " k";
  else s = Math.round(v).toLocaleString("fr-FR");
  return currency === "$" ? `$${s}` : `${s} ${currency}`;
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Math.round(v).toLocaleString("fr-FR");
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return (v * 100).toFixed(digits) + " %";
}

export function fmtGrowth(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = (v * 100).toFixed(1) + " %";
  return v > 0 ? "+" + s : s;
}

export function growthTone(v: number | null | undefined): "good" | "bad" | "muted" {
  if (v === null || v === undefined || Number.isNaN(v)) return "muted";
  if (v > 0.001) return "good";
  if (v < -0.001) return "bad";
  return "muted";
}
