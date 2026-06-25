"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const LINKS = [
  { href: "/", label: "Vue d'ensemble", icon: "🏠" },
  { href: "/analyse", label: "Analyse DCI", icon: "🔬" },
  { href: "/radar", label: "Radar opportunités", icon: "📡" },
  { href: "/pricing", label: "Prix par molécule", icon: "💰" },
  { href: "/opportunities", label: "Opportunités stratégiques", icon: "🧠" },
  { href: "/assistant", label: "Assistant IA", icon: "🤖" },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-1">
      {LINKS.map((l) => {
        const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            onClick={onNavigate}
            className={clsx(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
              active ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white",
            )}
          >
            <span className="text-base">{l.icon}</span>
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <div className="px-2">
      <div className="flex items-center gap-2 text-white">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg">💊</span>
        <div className="leading-tight">
          <div className="text-sm font-bold">Pharma Intelligence</div>
          <div className="text-[11px] text-slate-400">Algérie · IQVIA · PCH</div>
        </div>
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-6 bg-ink p-4 lg:flex">
      <Brand />
      <NavLinks />
      <div className="mt-auto px-2 text-[11px] leading-relaxed text-slate-500">
        Données IQVIA ville · PCH hospitalier · Nomenclature.
      </div>
    </aside>
  );
}

export function MobileBar() {
  const [open, setOpen] = useState(false);
  return (
    <div className="lg:hidden">
      <div className="sticky top-0 z-30 flex items-center justify-between bg-ink px-4 py-3">
        <Brand />
        <button
          onClick={() => setOpen(true)}
          aria-label="Ouvrir le menu"
          className="rounded-lg p-2 text-slate-200 hover:bg-white/10"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 6h18M3 12h18M3 18h18" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      {open && (
        <div className="fixed inset-0 z-40 flex" role="dialog">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="relative z-50 flex h-full w-72 max-w-[80%] flex-col gap-6 bg-ink p-4">
            <div className="flex items-center justify-between">
              <Brand />
              <button onClick={() => setOpen(false)} aria-label="Fermer" className="rounded-lg p-2 text-slate-300 hover:bg-white/10">
                ✕
              </button>
            </div>
            <NavLinks onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
