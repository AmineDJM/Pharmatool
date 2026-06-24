import type { ReactNode } from "react";

export function Hero({ badge, title, subtitle }: { badge?: string; title: string; subtitle?: ReactNode }) {
  return (
    <div className="mb-6 sm:mb-8">
      {badge && (
        <span className="mb-3 inline-flex items-center rounded-full bg-accent-soft px-3 py-1 text-xs font-semibold text-accent-fg ring-1 ring-inset ring-teal-200">
          {badge}
        </span>
      )}
      <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h1>
      {subtitle && <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-500 sm:text-base">{subtitle}</p>}
    </div>
  );
}
