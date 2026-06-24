"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { fmtMoney, fmtInt, fmtGrowth } from "@/lib/format";
import { Hero } from "@/components/Hero";
import { Card, Kpi, KpiGrid, DataTable, Spinner, ErrorState, Column } from "@/components/ui";

const VIEWS = [
  { id: "eligible", label: "Éligibles" },
  { id: "import_substitution", label: "Substitution import" },
  { id: "all", label: "Tout" },
];

const money$ = (v: any) => fmtMoney(v, "$");

export default function OpportunitiesPage() {
  const [view, setView] = useState("eligible");
  const [minUsd, setMinUsd] = useState(0);
  const [limit, setLimit] = useState(120);
  const { data, error, loading } = useAsync(() => api.opportunities(view, minUsd, limit), [view, minUsd, limit]);

  const cols: Column[] = [
    { key: "DCI", label: "DCI", className: "font-medium text-ink" },
    { key: "Opportunity score", label: "Score", align: "right", render: (v) => <b className="text-accent-fg">{v}</b> },
    { key: "Recommendation", label: "Recommandation" },
    { key: "Market value USD", label: "Marché", align: "right", render: money$ },
    { key: "Growth_PY", label: "Croissance", align: "right", render: (v) => fmtGrowth(v) },
    { key: "Manufacturers", label: "Fabricants", align: "right" },
    { key: "Importers", label: "Importateurs", align: "right" },
    { key: "Top market products", label: "Produits" },
  ];

  return (
    <div>
      <Hero badge="🧠 Strategic Opportunity Engine" title="Opportunités stratégiques produit"
        subtitle="Screening automatique des DCI à fort potentiel : taille de marché (IQVIA + PCH), croissance et intensité concurrentielle locale. Les marchés couverts uniquement par l'import sont priorisés." />

      <Card>
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <div className="flex flex-wrap gap-2">
            {VIEWS.map((v) => (
              <button key={v.id} onClick={() => setView(v.id)}
                className={`rounded-xl px-4 py-2 text-sm font-medium transition ${view === v.id ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>
                {v.label}
              </button>
            ))}
          </div>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">Marché min (USD)</span>
            <input type="number" className="input w-40" value={minUsd} step={250_000} min={0} onChange={(e) => setMinUsd(Number(e.target.value))} />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">Lignes max</span>
            <input type="number" className="input w-28" value={limit} step={20} min={20} max={500} onChange={(e) => setLimit(Number(e.target.value))} />
          </label>
        </div>

        {loading && <Spinner />}
        {error && <ErrorState message={error} />}
        {data && (
          <>
            <KpiGrid>
              <Kpi label="Opportunités" value={fmtInt(data.kpis.count)} hint="lignes" tone="accent" />
              <Kpi label="Valeur cumulée" value={money$(data.kpis.market_sum_usd)} hint="marché adressable" />
              <Kpi label="Substitution import" value={fmtInt(data.kpis.import_substitution)} hint="0 fabricant local" tone="good" />
              <Kpi label="Score médian" value={data.kpis.score_median?.toFixed?.(0) ?? "—"} hint="sur 100" />
            </KpiGrid>
            <div className="mt-5"><DataTable columns={cols} rows={data.rows} maxHeight={620} /></div>
          </>
        )}
      </Card>
    </div>
  );
}
