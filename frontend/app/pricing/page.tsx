"use client";

import { useState } from "react";
import { api, DciParams } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { useDebounced } from "@/lib/useDebounced";
import { fmtMoney, fmtInt, fmtGrowth } from "@/lib/format";
import { Hero } from "@/components/Hero";
import { DciSearch } from "@/components/DciSearch";
import { MultiSelect } from "@/components/MultiSelect";
import { Card, Kpi, KpiGrid, DataTable, Spinner, ErrorState, EmptyState, Section, Column } from "@/components/ui";

const moneyDZD = (v: any) => fmtMoney(v, "DZD");

function PriceStats({ stats, unit }: { stats: any; unit: string }) {
  if (!stats || !stats.n) return <EmptyState message="Aucune donnée de prix sur ce périmètre." />;
  return (
    <KpiGrid>
      <Kpi label="Prix moyen" value={moneyDZD(stats.avg_dzd)} hint={`≈ ${fmtMoney(stats.avg_usd, "$")} · ${unit}`} tone="accent" />
      <Kpi label="Médiane" value={moneyDZD(stats.median)} hint={unit} />
      <Kpi label="Minimum" value={moneyDZD(stats.min)} hint={unit} />
      <Kpi label="Maximum" value={moneyDZD(stats.max)} hint={unit} />
    </KpiGrid>
  );
}

export default function PricingPage() {
  const [dci, setDci] = useState<string[]>([]);
  const [dosage, setDosage] = useState<string[]>([]);
  const [forme, setForme] = useState<string[]>([]);
  const [lab, setLab] = useState<string[]>([]);
  const [tab, setTab] = useState<"ville" | "hosp">("ville");

  const has = dci.length > 0;
  const params: DciParams = { dci, dosage, forme, lab };
  const key = useDebounced(JSON.stringify(params), 300);

  const facets = useAsync(() => (has ? api.dciFacets(params) : Promise.resolve(null)), [key]);
  const price = useAsync(() => (has ? api.pricing(params) : Promise.resolve(null)), [key]);

  const f = facets.data;
  const p = price.data;

  const villeCols: Column[] = [
    { key: "BRAND", label: "Produit", className: "font-medium text-ink" },
    { key: "PRESENTATION", label: "Présentation" },
    { key: "LABORATOIRE", label: "Laboratoire" },
    { key: "Prix_boite_DZD", label: "Prix boîte", align: "right", render: moneyDZD },
    { key: "MARKET_VALUE_DZD", label: "Valeur", align: "right", render: moneyDZD },
    { key: "GROWTH_PY", label: "Croissance", align: "right", render: (v) => fmtGrowth(v) },
  ];
  const hospCols: Column[] = [
    { key: "PRODUCT_FULL", label: "Produit", className: "font-medium text-ink" },
    { key: "LABORATOIRE", label: "Fournisseur" },
    { key: "QTE", label: "Quantité", align: "right", render: (v) => fmtInt(v) },
    { key: "Prix_unitaire_DZD", label: "Prix unitaire", align: "right", render: moneyDZD },
    { key: "DEVISE", label: "Devise" },
    { key: "DATESTOCKAGE", label: "Réception" },
  ];

  return (
    <div>
      <Hero
        badge="💰 Pricing Intelligence"
        title="Prix par molécule"
        subtitle="Cherche une molécule, affine par dosage / forme / laboratoire, et obtiens le prix marché ville (IQVIA, prix/boîte) et hospitalier (PCH, prix/unité)."
      />

      <Card>
        <DciSearch selected={dci} onChange={setDci} />
        {has && (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <MultiSelect label="Dosage" options={f?.dosage ?? []} selected={dosage} onChange={setDosage} />
            <MultiSelect label="Forme" options={f?.forme ?? []} selected={forme} onChange={setForme} />
            <MultiSelect label="Laboratoire" options={f?.lab ?? []} selected={lab} onChange={setLab} />
          </div>
        )}
      </Card>

      {!has && <div className="mt-6"><EmptyState message="👆 Cherche une molécule pour obtenir son prix." /></div>}
      {has && price.loading && <div className="mt-6"><Spinner label="Calcul des prix…" /></div>}
      {has && price.error && <div className="mt-6"><ErrorState message={price.error} /></div>}

      {has && p && !price.loading && (
        <div className="mt-6">
          <div className="mb-4 flex flex-wrap gap-2">
            <button onClick={() => setTab("ville")} className={`rounded-xl px-4 py-2 text-sm font-medium transition ${tab === "ville" ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>🏙️ Prix marché ville (IQVIA)</button>
            <button onClick={() => setTab("hosp")} className={`rounded-xl px-4 py-2 text-sm font-medium transition ${tab === "hosp" ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>🏥 Prix hospitalier (PCH)</button>
          </div>
          <Card>
            {tab === "ville" ? (
              <>
                <PriceStats stats={p.ville} unit="prix / boîte" />
                <div className="mt-5"><Section title="Prix par produit" /><DataTable columns={villeCols} rows={p.ville_rows} maxHeight={400} /></div>
              </>
            ) : (
              <>
                <PriceStats stats={p.hospital} unit="prix / unité" />
                <div className="mt-5"><Section title="Réceptions hospitalières" /><DataTable columns={hospCols} rows={p.hospital_rows} maxHeight={400} /></div>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
