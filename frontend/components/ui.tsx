import clsx from "clsx";
import type { ReactNode } from "react";

/* ---------- Card ---------- */
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("card p-5 sm:p-6", className)}>{children}</div>;
}

/* ---------- Section heading ---------- */
export function Section({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-ink sm:text-xl">{title}</h2>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-slate-500">{subtitle}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

/* ---------- KPI ---------- */
type Tone = "good" | "bad" | "muted" | "accent";
const toneText: Record<Tone, string> = {
  good: "text-emerald-600",
  bad: "text-rose-600",
  muted: "text-slate-500",
  accent: "text-accent-fg",
};

export function Kpi({
  label,
  value,
  hint,
  tone = "muted",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: Tone;
}) {
  return (
    <div className="card p-4 sm:p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1.5 text-2xl font-bold tracking-tight text-ink sm:text-[1.7rem]">{value}</div>
      {hint && <div className={clsx("mt-1 text-xs font-medium", toneText[tone])}>{hint}</div>}
    </div>
  );
}

export function KpiGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">{children}</div>;
}

/* ---------- Badge / chip ---------- */
export function Badge({ children, tone = "muted" }: { children: ReactNode; tone?: Tone }) {
  const map: Record<Tone, string> = {
    good: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    bad: "bg-rose-50 text-rose-700 ring-rose-200",
    muted: "bg-slate-100 text-slate-600 ring-slate-200",
    accent: "bg-accent-soft text-accent-fg ring-teal-200",
  };
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset", map[tone])}>
      {children}
    </span>
  );
}

/* ---------- Data table ---------- */
export type Column = {
  key: string;
  label: string;
  align?: "left" | "right";
  render?: (v: any, row: Record<string, any>) => ReactNode;
  className?: string;
};

export function DataTable({
  columns,
  rows,
  maxHeight = 460,
}: {
  columns: Column[];
  rows: Record<string, any>[];
  maxHeight?: number;
}) {
  if (!rows.length) return <EmptyState />;
  return (
    <div className="scroll-thin overflow-auto rounded-xl border border-slate-200" style={{ maxHeight }}>
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={clsx("whitespace-nowrap px-3 py-2.5 font-semibold", c.align === "right" && "text-right")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, i) => (
            <tr key={i} className="transition hover:bg-slate-50/70">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={clsx(
                    "px-3 py-2.5 align-top",
                    c.align === "right" && "text-right tabular-nums",
                    c.className,
                  )}
                >
                  {c.render ? c.render(row[c.key], row) : fallback(row[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function fallback(v: any): ReactNode {
  if (v === null || v === undefined || v === "") return <span className="text-slate-300">—</span>;
  return String(v);
}

/* ---------- States ---------- */
export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-accent" />
      {label || "Chargement…"}
    </div>
  );
}

export function EmptyState({ message = "Aucune donnée pour ces critères." }: { message?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-4 py-10 text-center text-sm text-slate-500">
      {message}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm text-rose-700">
      <b>Erreur.</b> {message}
    </div>
  );
}
