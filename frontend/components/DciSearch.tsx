"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export function DciSearch({ selected, onChange }: { selected: string[]; onChange: (next: string[]) => void }) {
  const [q, setQ] = useState("");
  const [opts, setOpts] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      api.dciOptions(q).then((r) => setOpts(r.candidates || [])).catch(() => setOpts([])).finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  function add(d: string) {
    if (!selected.includes(d)) onChange([...selected, d]);
    setQ("");
  }

  const shown = opts.filter((o) => !selected.includes(o));

  return (
    <div className="relative" ref={ref}>
      <input
        className="input text-base"
        placeholder="Chercher une molécule (DCI) — ex : amoxicilline, dolutégravir, paracétamol"
        value={q}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
      />
      {open && (q.length > 0 || shown.length > 0) && (
        <div className="scroll-thin absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
          {loading && <div className="px-3 py-2 text-xs text-slate-400">Recherche…</div>}
          {!loading && shown.length === 0 && <div className="px-3 py-2 text-xs text-slate-400">Aucune DCI trouvée.</div>}
          {shown.slice(0, 50).map((o) => (
            <button key={o} type="button" onClick={() => add(o)} className="block w-full truncate rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50">
              {o}
            </button>
          ))}
        </div>
      )}
      {selected.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {selected.map((d) => (
            <span key={d} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-2.5 py-1 text-xs font-medium text-white">
              🧬 {d}
              <button type="button" onClick={() => onChange(selected.filter((x) => x !== d))} className="text-white/70 hover:text-white">✕</button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
