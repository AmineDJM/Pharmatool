"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { api, DciParams } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { useDebounced } from "@/lib/useDebounced";
import { fmtMoney, fmtInt, fmtGrowth, fmtPct, growthTone } from "@/lib/format";
import { Hero } from "@/components/Hero";
import { DciSearch } from "@/components/DciSearch";
import { MultiSelect } from "@/components/MultiSelect";
import { Card, Kpi, KpiGrid, Section, DataTable, Spinner, ErrorState, EmptyState, Badge, Column } from "@/components/ui";

const ChartSkeleton = () => <div className="grid h-[280px] place-items-center text-sm text-slate-400">Graphique…</div>;
const ShareDonut = dynamic(() => import("@/components/CompetitionCharts").then((m) => m.ShareDonut), { ssr: false, loading: ChartSkeleton });
const GrowthBars = dynamic(() => import("@/components/CompetitionCharts").then((m) => m.GrowthBars), { ssr: false, loading: ChartSkeleton });

const MARKETS = [
  { id: "iqvia", label: "🏙️ Ville (IQVIA)" },
  { id: "pch", label: "🏥 Hôpital (PCH)" },
];

const moneyDZD = (v: any) => fmtMoney(v, "DZD");

export default function AnalysePage() {
  const [dci, setDci] = useState<string[]>([]);
  const [markets, setMarkets] = useState<string[]>(["iqvia", "pch"]);
  const [dosage, setDosage] = useState<string[]>([]);
  const [forme, setForme] = useState<string[]>([]);
  const [lab, setLab] = useState<string[]>([]);
  const [mtab, setMtab] = useState<"ville" | "hosp">("ville");

  const has = dci.length > 0;
  const params: DciParams = { dci, markets, dosage, forme, lab };
  const key = useDebounced(JSON.stringify(params), 300);

  const facets = useAsync(() => (has ? api.dciFacets(params) : Promise.resolve(null)), [key]);
  const analysis = useAsync(() => (has ? api.dciAnalysis(params) : Promise.resolve(null)), [key]);

  const f = facets.data;
  const a = analysis.data;

  const compCols: Column[] = [
    { key: "LABORATOIRE", label: "Laboratoire", className: "font-medium text-ink" },
    { key: "Share", label: "Part de marché", align: "right", render: (v) => <b className="text-accent-fg">{fmtPct(v)}</b> },
    { key: "Value_DZD", label: "Valeur", align: "right", render: moneyDZD },
    { key: "Growth_PY", label: "Croissance", align: "right", render: (v) => fmtGrowth(v) },
    { key: "Volume", label: "Volume", align: "right", render: (v) => fmtInt(v) },
  ];
  const marketCols: Column[] = [
    { key: "Produit", label: "Produit", className: "font-medium text-ink" },
    { key: "Laboratoire", label: "Laboratoire" },
    { key: "Classe", label: "Classe" },
    { key: "Volume", label: "Volume", align: "right", render: (v) => fmtInt(v) },
    { key: "Valeur DZD", label: "Valeur", align: "right", render: moneyDZD },
    { key: "Croissance", label: "Croissance", align: "right", render: (v) => fmtGrowth(v) },
  ];

  function toggleMarket(id: string) {
    setMarkets((m) => (m.includes(id) ? m.filter((x) => x !== id) : [...m, id]));
  }

  return (
    <div>
      <Hero
        badge="🔬 Analyse produit & DCI"
        title="Analyse complète d'une molécule"
        subtitle="Recherche par DCI avec filtres connectés (dosage, forme, laboratoire) : taille de marché ville + hôpital, paysage concurrentiel, parts de marché de chaque acteur, croissance et empreinte locale vs import."
      />

      <Card>
        <DciSearch selected={dci} onChange={setDci} />

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-slate-500">Marché :</span>
          {MARKETS.map((m) => (
            <button
              key={m.id}
              onClick={() => toggleMarket(m.id)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ring-1 transition ${
                markets.includes(m.id) ? "bg-ink text-white ring-ink" : "bg-white text-slate-500 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {has && (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <MultiSelect label="Dosage" options={f?.dosage ?? []} selected={dosage} onChange={setDosage} />
            <MultiSelect label="Forme" options={f?.forme ?? []} selected={forme} onChange={setForme} />
            <MultiSelect label="Laboratoire" options={f?.lab ?? []} selected={lab} onChange={setLab} />
          </div>
        )}
        {has && f && (
          <p className="mt-3 text-xs text-slate-400">
            {fmtInt(f.n_candidates)} références correspondantes · Nomenclature {fmtInt(f.n_nomenclature)} · IQVIA {fmtInt(f.n_iqvia)} · PCH {fmtInt(f.n_pch)}
          </p>
        )}
      </Card>

      {!has && (
        <div className="mt-6">
          <EmptyState message="👆 Cherche une molécule (DCI) pour lancer l'analyse de marché." />
        </div>
      )}

      {has && analysis.loading && <div className="mt-6"><Spinner label="Agrégation des marchés et calcul de la concurrence…" /></div>}
      {has && analysis.error && <div className="mt-6"><ErrorState message={analysis.error} /></div>}
      {has && a?.empty && <div className="mt-6"><EmptyState message="Aucun marché exploitable pour cette molécule avec ces filtres. Élargis les filtres ou retire un marché." /></div>}

      {has && a && !a.empty && !analysis.loading && (
        <div className="mt-6 space-y-6">
          <KpiGrid>
            <Kpi label="Marché total" value={moneyDZD(a.kpis.value_dzd)} hint={`≈ ${fmtMoney(a.kpis.value_usd, "$")}`} tone="accent" />
            <Kpi label="Croissance vs N-1" value={fmtGrowth(a.kpis.growth)} hint="valeur pondérée" tone={growthTone(a.kpis.growth)} />
            <Kpi label="Volume" value={fmtInt(a.kpis.volume)} hint="unités / réceptions" />
            <Kpi label="Concurrents" value={fmtInt(a.kpis.n_competitors)} hint={`${a.kpis.hhi_label} · HHI ${fmtInt(a.kpis.hhi)}`} />
          </KpiGrid>

          <div className="flex flex-wrap gap-2">
            <Badge tone={a.origin.n_local ? "good" : "muted"}>🏭 {a.origin.n_local} fabricant(s) local(aux)</Badge>
            <Badge tone="muted">📦 {a.origin.n_import} importateur(s)</Badge>
            <Badge tone={(a.kpis.hhi ?? 0) >= 2500 ? "bad" : "good"}>📊 {a.kpis.hhi_label}</Badge>
          </div>

          <Card>
            <Section title="🏟️ Paysage concurrentiel" subtitle="Parts de marché et croissance de chaque acteur (ville + hôpital cumulés)." />
            <div className="grid gap-6 lg:grid-cols-2">
              <div>
                <div className="mb-2 text-sm font-medium text-slate-500">Parts de marché (valeur)</div>
                <ShareDonut data={a.competitors} />
              </div>
              <div>
                <div className="mb-2 text-sm font-medium text-slate-500">Croissance des principaux acteurs</div>
                <GrowthBars data={a.competitors} />
              </div>
            </div>
            <div className="mt-5">
              <DataTable columns={compCols} rows={a.competitors} maxHeight={360} />
            </div>
            {(a.origin.local_labs.length > 0 || a.origin.import_labs.length > 0) && (
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl bg-emerald-50/60 p-4">
                  <div className="mb-2 text-sm font-semibold text-emerald-700">🏭 Fabricants locaux ({a.origin.n_local})</div>
                  <div className="text-sm text-slate-600">{a.origin.local_labs.join(" · ") || "Aucun"}</div>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <div className="mb-2 text-sm font-semibold text-slate-600">📦 Importateurs ({a.origin.n_import})</div>
                  <div className="text-sm text-slate-600">{a.origin.import_labs.join(" · ") || "Aucun"}</div>
                </div>
              </div>
            )}
          </Card>

          <Card>
            <div className="mb-4 flex flex-wrap gap-2">
              <button onClick={() => setMtab("ville")} className={`rounded-xl px-4 py-2 text-sm font-medium transition ${mtab === "ville" ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>
                🏙️ Marché ville ({a.n_ville})
              </button>
              <button onClick={() => setMtab("hosp")} className={`rounded-xl px-4 py-2 text-sm font-medium transition ${mtab === "hosp" ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>
                🏥 Hospitalier PCH ({a.n_hosp})
              </button>
            </div>
            <DataTable columns={marketCols} rows={mtab === "ville" ? a.ville_rows : a.hospital_rows} maxHeight={460} />
          </Card>
        </div>
      )}
    </div>
  );
}
