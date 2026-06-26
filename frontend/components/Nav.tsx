"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { clearPw } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Vue d'ensemble", icon: "🏠" },
  { href: "/analyse", label: "Analyse DCI", icon: "🔬" },
  { href: "/pricing", label: "Prix par molécule", icon: "💰" },
  { href: "/radar", label: "Radar opportunités", icon: "📡" },
  { href: "/opportunities", label: "Opportunités stratégiques", icon: "🧠" },
  { href: "/assistant", label: "Assistant IA", icon: "🤖" },
];

// Primary tabs shown in the mobile bottom bar (the rest live under "Plus").
const PRIMARY = ["/", "/analyse", "/pricing", "/radar"];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function logout() {
  clearPw();
  window.dispatchEvent(new Event("pt-unauth"));
}

function Brand() {
  return (
    <div className="flex items-center gap-2 text-white">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg">💊</span>
      <div className="leading-tight">
        <div className="text-sm font-bold">Pharma Intelligence</div>
        <div className="text-[11px] text-slate-400">Algérie · IQVIA · PCH</div>
      </div>
    </div>
  );
}

/* ---------------- Desktop sidebar ---------------- */
export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-6 bg-ink p-4 lg:flex">
      <div className="px-2"><Brand /></div>
      <nav className="flex flex-col gap-1">
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={clsx(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
              isActive(pathname, l.href) ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white",
            )}
          >
            <span className="text-base">{l.icon}</span>
            {l.label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto px-2">
        <button onClick={logout} className="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white">
          <span className="text-base">🔒</span> Déconnexion
        </button>
      </div>
    </aside>
  );
}

/* ---------------- Mobile: top bar + bottom tabs + drawer ---------------- */
export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <div className="lg:hidden">
      {/* Slim top brand bar */}
      <div className="sticky top-0 z-30 flex items-center justify-between bg-ink px-4 py-3">
        <Brand />
      </div>

      {/* Bottom tab bar */}
      <div className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] shadow-[0_-4px_20px_-12px_rgba(15,23,42,.25)]">
        {LINKS.filter((l) => PRIMARY.includes(l.href)).map((l) => {
          const active = isActive(pathname, l.href);
          return (
            <Link key={l.href} href={l.href} className={clsx("flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition", active ? "text-accent-fg" : "text-slate-500")}>
              <span className="text-xl leading-none">{l.icon}</span>
              {l.label.split(" ")[0]}
            </Link>
          );
        })}
        <button onClick={() => setOpen(true)} className="flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium text-slate-500">
          <span className="text-xl leading-none">⋯</span>
          Plus
        </button>
      </div>

      {/* Drawer (full menu) */}
      {open && (
        <div className="fixed inset-0 z-50 flex" role="dialog">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="relative z-10 ml-auto flex h-full w-72 max-w-[82%] flex-col gap-5 bg-ink p-4">
            <div className="flex items-center justify-between">
              <Brand />
              <button onClick={() => setOpen(false)} aria-label="Fermer" className="rounded-lg p-2 text-slate-300 hover:bg-white/10">✕</button>
            </div>
            <nav className="flex flex-col gap-1">
              {LINKS.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className={clsx(
                    "flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition",
                    isActive(pathname, l.href) ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white",
                  )}
                >
                  <span className="text-base">{l.icon}</span>
                  {l.label}
                </Link>
              ))}
            </nav>
            <button onClick={logout} className="mt-auto flex items-center gap-2 rounded-xl px-3 py-3 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white">
              <span className="text-base">🔒</span> Déconnexion
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
