import clsx from "clsx";

export type BarItem = { label: string; value: number; display?: string; tone?: "accent" | "good" | "bad" };

function toneClass(t?: BarItem["tone"]) {
  if (t === "good") return "bg-emerald-500";
  if (t === "bad") return "bg-rose-400";
  return "bg-accent";
}

export function BarList({ items, formatValue }: { items: BarItem[]; formatValue?: (v: number) => string }) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.value || 0)));
  if (!items.length) return null;
  return (
    <div className="space-y-3">
      {items.map((it, i) => (
        <div key={i}>
          <div className="mb-1 flex items-center justify-between gap-3">
            <span className="truncate text-sm text-slate-700">{it.label}</span>
            <span className="shrink-0 text-xs font-semibold tabular-nums text-slate-500">
              {it.display ?? (formatValue ? formatValue(it.value) : String(it.value))}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={clsx("h-full rounded-full", toneClass(it.tone))}
              style={{ width: `${Math.max(2, (Math.abs(it.value || 0) / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
