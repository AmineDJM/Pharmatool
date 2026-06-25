"use client";

import clsx from "clsx";
import { useEffect, useRef, useState } from "react";

export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  placeholder = "Tous",
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const disabled = options.length === 0 && selected.length === 0;

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const filtered = q ? options.filter((o) => o.toLowerCase().includes(q.toLowerCase())) : options;

  function toggle(opt: string) {
    onChange(selected.includes(opt) ? selected.filter((x) => x !== opt) : [...selected, opt]);
  }

  return (
    <div className="relative" ref={ref}>
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "flex w-full items-center justify-between gap-2 rounded-xl border bg-white px-3 py-2.5 text-left text-sm transition",
          "border-slate-300 hover:border-slate-400 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400",
          open && "border-accent ring-2 ring-accent/20",
        )}
      >
        <span className={clsx("truncate", selected.length ? "text-ink" : "text-slate-400")}>
          {selected.length === 0 ? placeholder : selected.length === 1 ? selected[0] : `${selected.length} sélectionnés`}
        </span>
        <span className="shrink-0 text-slate-400">▾</span>
      </button>

      {selected.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {selected.map((s) => (
            <span key={s} className="inline-flex max-w-full items-center gap-1 rounded-md bg-accent-soft px-2 py-0.5 text-xs text-accent-fg">
              <span className="max-w-[160px] truncate">{s}</span>
              <button type="button" onClick={() => toggle(s)} className="shrink-0 text-accent-fg/70 hover:text-accent-fg">✕</button>
            </span>
          ))}
        </div>
      )}

      {open && (
        <div className="absolute z-30 mt-1 w-full min-w-[240px] rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Rechercher…"
            className="mb-2 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm outline-none focus:border-accent"
          />
          <div className="scroll-thin max-h-60 overflow-auto">
            {filtered.length === 0 && <div className="px-2 py-3 text-center text-xs text-slate-400">Aucune option</div>}
            {filtered.slice(0, 300).map((o) => {
              const on = selected.includes(o);
              return (
                <button
                  key={o}
                  type="button"
                  onClick={() => toggle(o)}
                  className={clsx("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition hover:bg-slate-50", on && "bg-accent-soft/60")}
                >
                  <span className={clsx("grid h-4 w-4 shrink-0 place-items-center rounded border text-[10px]", on ? "border-accent bg-accent text-white" : "border-slate-300")}>
                    {on ? "✓" : ""}
                  </span>
                  <span className="truncate">{o}</span>
                </button>
              );
            })}
          </div>
          {selected.length > 0 && (
            <button type="button" onClick={() => onChange([])} className="mt-2 w-full rounded-lg px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-50">
              Tout effacer
            </button>
          )}
        </div>
      )}
    </div>
  );
}
