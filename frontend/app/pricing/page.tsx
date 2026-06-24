"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtMoney, fmtInt, fmtGrowth } from "@/lib/format";
import { Hero } from "@/components/Hero";
import { Card, Kpi, KpiGrid, DataTable, Spinner, ErrorState, Badge, Section, EmptyState, Column } from "@/components/ui";

type Parsed = { dci_candidates: string[]; dosage: string[]; forme: string[] };

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
  const [query, setQuery] = useState("");
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [dci, setDci] = useState("");
  const [useDosage, setUseDosage] = useState(false);
  const [useForme, setUseForme] = useState(false);
  const [price, setPrice] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"ville" | "hosp">("ville");

  useEffect(() => {
    const q = query.trim();
    if (!q) { setParsed(null); setPrice(null); setError(null); return; }
    const t = setTimeout(() => {
      api.pricingSuggest(q).then((p: Parsed) => {
        setParsed(p);
        setDci(p.dci_candidates?.[0] || "");
        setUseDosage(!!p.dosage?.length);
        setUseForme(!!p.forme?.length);
      }).catch((e) => setError(e.message));
    }, 350);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!dci) { setPrice(null); return; }
    let alive = true;
    setLoading(true); setError(null);
    const dosage = useDosage && parsed?.dosage?.length ? parsed.dosage.join(",") : undefined;
    const forme = useForme && parsed?.forme?.length ? parsed.forme.join(",") : undefined;
    api.pricing(dci, dosage, forme)
      .then((d) => alive && setPrice(d))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [dci, useDosage, useForme, parsed]);

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
      <Hero badge="💰 Pricing Intelligence" title="Prix par molécule"
        subtitle="Tape une molécule (avec dosage et forme si tu veux) : l'outil reconnaît la DCI, le dosage et la forme, puis te donne le prix marché ville (IQVIA) et hospitalier (PCH)." />

      <Card>
        <input className="input text-base" placeholder="ex : amoxicilline 500 mg comprimé   ·   paracetamol 1 g   ·   insuline glargine"
          value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />

        {!query.trim() && <p className="mt-4 text-sm text-slate-500">👆 Tape une molécule pour obtenir son prix.</p>}

        {parsed && parsed.dci_candidates.length === 0 && (
          <p className="mt-4 text-sm text-amber-600">Aucune DCI reconnue. Essaie une autre orthographe.</p>
        )}

        {parsed && parsed.dci_candidates.length > 0 && (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="accent">🧬 DCI : {dci || parsed.dci_candidates[0]}</Badge>
              {parsed.dosage?.length > 0 && <Badge>💊 {parsed.dosage.join(", ")}</Badge>}
              {parsed.forme?.length > 0 && <Badge>🧪 {parsed.forme.join(", ")}</Badge>}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-slate-500">DCI</span>
                <select className="input" value={dci} onChange={(e) => setDci(e.target.value)}>
                  {parsed.dci_candidates.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </label>
              <label className="flex items-end gap-2 pb-2.5 text-sm text-slate-600">
                <input type="checkbox" className="h-4 w-4 accent-teal-600" checked={useDosage} disabled={!parsed.dosage?.length} onChange={(e) => setUseDosage(e.target.checked)} />
                Filtrer le dosage
              </label>
              <label className="flex items-end gap-2 pb-2.5 text-sm text-slate-600">
                <input type="checkbox" className="h-4 w-4 accent-teal-600" checked={useForme} disabled={!parsed.forme?.length} onChange={(e) => setUseForme(e.target.checked)} />
                Filtrer la forme
              </label>
            </div>
          </div>
        )}
      </Card>

      {error && <div className="mt-5"><ErrorState message={error} /></div>}
      {loading && <div className="mt-5"><Spinner label="Calcul des prix…" /></div>}

      {price && !loading && (
        <div className="mt-5">
          <div className="mb-4 flex flex-wrap gap-2">
            <button onClick={() => setTab("ville")} className={`rounded-xl px-4 py-2 text-sm font-medium transition ${tab === "ville" ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>🏙️ Prix marché ville (IQVIA)</button>
            <button onClick={() => setTab("hosp")} className={`rounded-xl px-4 py-2 text-sm font-medium transition ${tab === "hosp" ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>🏥 Prix hospitalier (PCH)</button>
          </div>
          <Card>
            {tab === "ville" ? (
              <>
                <PriceStats stats={price.ville} unit="prix / boîte" />
                <div className="mt-5"><Section title="Prix par produit" /><DataTable columns={villeCols} rows={price.ville_rows} maxHeight={380} /></div>
              </>
            ) : (
              <>
                <PriceStats stats={price.hospital} unit="prix / unité" />
                <div className="mt-5"><Section title="Réceptions hospitalières" /><DataTable columns={hospCols} rows={price.hospital_rows} maxHeight={380} /></div>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
