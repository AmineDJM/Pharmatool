"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { fmtMoney, fmtInt, fmtGrowth } from "@/lib/format";
import { Hero } from "@/components/Hero";
import { Card, Kpi, KpiGrid, DataTable, Spinner, ErrorState, Column } from "@/components/ui";

const TABS = [
  { id: "new", label: "🆕 Nouveaux enregistrements" },
  { id: "white", label: "⚪ White spaces" },
  { id: "exp", label: "⏳ Expirations" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function NumberField({ label, value, onChange, step = 1, min = 0, suffix }: {
  label: string; value: number; onChange: (v: number) => void; step?: number; min?: number; suffix?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      <div className="flex items-center gap-2">
        <input type="number" className="input" value={value} min={min} step={step}
          onChange={(e) => onChange(Number(e.target.value))} />
        {suffix && <span className="text-xs text-slate-400">{suffix}</span>}
      </div>
    </label>
  );
}

const money$ = (v: any) => fmtMoney(v, "$");
const growth = (v: any) => fmtGrowth(v);

function NewRegistrations() {
  const [months, setMonths] = useState(6);
  const [minUsd, setMinUsd] = useState(500_000);
  const [maxComp, setMaxComp] = useState(2);
  const { data, error, loading } = useAsync(() => api.radarNew(months, minUsd, maxComp), [months, minUsd, maxComp]);

  const cols: Column[] = [
    { key: "DCI", label: "DCI", className: "font-medium text-ink" },
    { key: "Last_registration", label: "Enregistré le" },
    { key: "Market value USD", label: "Marché", align: "right", render: money$ },
    { key: "Growth_PY", label: "Croissance", align: "right", render: growth },
    { key: "Concurrents", label: "Concurrents", align: "right" },
    { key: "Manufacturers", label: "Fabricants", align: "right" },
    { key: "Importers", label: "Importateurs", align: "right" },
    { key: "Top market products", label: "Produits" },
  ];

  return (
    <Card>
      <p className="mb-4 text-sm text-slate-500">DCI enregistrées récemment, sur un marché attractif et encore peu disputé. Tous les seuils sont ajustables.</p>
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <NumberField label="Enregistré il y a moins de" value={months} onChange={setMonths} min={1} suffix="mois" />
        <NumberField label="Marché minimum (USD)" value={minUsd} onChange={setMinUsd} step={100_000} />
        <NumberField label="Concurrents maximum" value={maxComp} onChange={setMaxComp} />
      </div>
      {loading && <Spinner />}
      {error && <ErrorState message={error} />}
      {data && (
        <>
          <KpiGrid>
            <Kpi label="Opportunités" value={fmtInt(data.kpis.count)} hint={`≤ ${months} mois · ≤ ${maxComp} conc.`} tone="accent" />
            <Kpi label="Marché cumulé" value={money$(data.kpis.market_sum_usd)} hint="adressable" />
            <Kpi label="Sans fabricant local" value={fmtInt(data.kpis.white_space)} hint="white space" />
            <Kpi label="Marché médian" value={money$(data.kpis.market_median_usd)} hint="par opportunité" />
          </KpiGrid>
          <div className="mt-5"><DataTable columns={cols} rows={data.rows} /></div>
        </>
      )}
    </Card>
  );
}

function WhiteSpaces() {
  const [minUsd, setMinUsd] = useState(300_000);
  const { data, error, loading } = useAsync(() => api.radarWhite(minUsd), [minUsd]);
  const cols: Column[] = [
    { key: "DCI", label: "DCI", className: "font-medium text-ink" },
    { key: "Market value USD", label: "Marché", align: "right", render: money$ },
    { key: "Growth_PY", label: "Croissance", align: "right", render: growth },
    { key: "Importers", label: "Importateurs", align: "right" },
    { key: "Importer labs", label: "Importateurs (labos)" },
    { key: "Top market products", label: "Produits" },
  ];
  return (
    <Card>
      <p className="mb-4 text-sm text-slate-500">Demande réelle (marché IQVIA/PCH) mais aucun fabricant local : cibles prioritaires de production locale / substitution import.</p>
      <div className="mb-5 max-w-xs"><NumberField label="Marché minimum (USD)" value={minUsd} onChange={setMinUsd} step={100_000} /></div>
      {loading && <Spinner />}
      {error && <ErrorState message={error} />}
      {data && (
        <>
          <KpiGrid>
            <Kpi label="White spaces" value={fmtInt(data.kpis.count)} tone="accent" />
            <Kpi label="Marché cumulé" value={money$(data.kpis.market_sum_usd)} hint="adressable" />
            <Kpi label="Avec demande import" value={fmtInt(data.kpis.with_import_demand)} hint="substitution" />
            <Kpi label="Marché médian" value={money$(data.kpis.market_median_usd)} hint="par molécule" />
          </KpiGrid>
          <div className="mt-5"><DataTable columns={cols} rows={data.rows} /></div>
        </>
      )}
    </Card>
  );
}

function Expirations() {
  const [validity, setValidity] = useState(5);
  const [horizon, setHorizon] = useState(24);
  const { data, error, loading } = useAsync(() => api.radarExpirations(validity, horizon), [validity, horizon]);
  const cols: Column[] = [
    { key: "DCI", label: "DCI", className: "font-medium text-ink" },
    { key: "Produit", label: "Produit" },
    { key: "Laboratoire", label: "Laboratoire" },
    { key: "Origine", label: "Origine" },
    { key: "Forme", label: "Forme" },
    { key: "Dosage", label: "Dosage" },
    { key: "Echeance_estimee", label: "Échéance estimée" },
  ];
  return (
    <Card>
      <p className="mb-4 text-sm text-slate-500">Produits dont l'enregistrement arrive à échéance (estimée = dernière décision + validité) — fenêtre d'opportunité si un concurrent ne renouvelle pas.</p>
      <div className="mb-5 grid max-w-md gap-3 sm:grid-cols-2">
        <NumberField label="Validité d'un enregistrement (ans)" value={validity} onChange={setValidity} min={1} />
        <NumberField label="Horizon (mois)" value={horizon} onChange={setHorizon} min={1} />
      </div>
      {loading && <Spinner />}
      {error && <ErrorState message={error} />}
      {data && (
        <>
          <KpiGrid>
            <Kpi label="Produits concernés" value={fmtInt(data.kpis.count)} hint={`≤ ${horizon} mois`} tone="accent" />
            <Kpi label="DCI distinctes" value={fmtInt(data.kpis.n_dci)} hint="molécules" />
            <Kpi label="Laboratoires" value={fmtInt(data.kpis.n_labs)} hint="détenteurs" />
            <Kpi label="Dont importés" value={fmtInt(data.kpis.imported)} hint="origine import" />
          </KpiGrid>
          <div className="mt-5"><DataTable columns={cols} rows={data.rows} /></div>
        </>
      )}
    </Card>
  );
}

export default function RadarPage() {
  const [tab, setTab] = useState<TabId>("new");
  return (
    <div>
      <Hero badge="📡 Opportunity Radar" title="Radar opportunités"
        subtitle="Trois signaux automatiques : nouveaux enregistrements à fort potentiel, échéances de renouvellement, et marchés sans fabricant local." />
      <div className="mb-5 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`rounded-xl px-4 py-2 text-sm font-medium transition ${tab === t.id ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "new" && <NewRegistrations />}
      {tab === "white" && <WhiteSpaces />}
      {tab === "exp" && <Expirations />}
    </div>
  );
}
