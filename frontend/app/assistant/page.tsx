"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { fmtMoney, fmtInt, fmtGrowth } from "@/lib/format";
import { Hero } from "@/components/Hero";
import { Card, Kpi, KpiGrid, DataTable, Spinner, ErrorState, Badge, Column } from "@/components/ui";

const EXAMPLES = [
  "Molécules en croissance > 10% avec un marché > 5M USD et moins de 2 fabricants locaux",
  "Top 10 des plus gros marchés sans fabricant local",
  "Opportunités de substitution import les plus rentables",
  "Marchés > 3M USD qui déclinent (croissance négative)",
];

const money$ = (v: any) => fmtMoney(v, "$");

export default function AssistantPage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noKey, setNoKey] = useState(false);

  async function ask(q: string) {
    const text = q.trim();
    if (!text) return;
    setLoading(true); setError(null); setNoKey(false); setResult(null);
    try {
      const r = await api.assistant(text);
      setResult(r);
    } catch (e: any) {
      if (String(e?.message).includes("no_key")) setNoKey(true);
      else setError(e?.message || "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }

  const cols: Column[] = [
    { key: "DCI", label: "DCI", className: "font-medium text-ink" },
    { key: "Market value USD", label: "Marché", align: "right", render: money$ },
    { key: "Growth_PY", label: "Croissance", align: "right", render: (v) => fmtGrowth(v) },
    { key: "Manufacturers", label: "Fabricants", align: "right" },
    { key: "Importers", label: "Importateurs", align: "right" },
    { key: "Opportunity score", label: "Score", align: "right" },
    { key: "Recommendation", label: "Recommandation" },
  ];

  return (
    <div>
      <Hero badge="🤖 AI Assistant · Claude Haiku" title="Assistant intelligent"
        subtitle="Pose ta question en français — l'assistant comprend ce que tu cherches et filtre le marché pour toi. Il ne lit que tes données, il n'invente aucun chiffre." />

      <Card>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row">
          <input className="input text-base" placeholder="ex : top 10 des marchés > 2M USD sans fabricant local"
            value={question} onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask(question)} />
          <button className="btn-primary shrink-0" onClick={() => ask(question)} disabled={loading}>🤖 Demander</button>
        </div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => { setQuestion(ex); ask(ex); }}
              className="rounded-full bg-slate-100 px-3 py-1.5 text-left text-xs text-slate-600 transition hover:bg-slate-200">
              {ex}
            </button>
          ))}
        </div>
      </Card>

      {loading && <div className="mt-5"><Spinner label="L'assistant analyse ta question…" /></div>}
      {error && <div className="mt-5"><ErrorState message={error} /></div>}

      {noKey && (
        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
          <b>🔑 Assistant IA non configuré.</b>
          <p className="mt-2">Pour l'activer, ajoute ta clé Anthropic dans les variables d'environnement du service sur Render :</p>
          <pre className="mt-2 overflow-auto rounded-lg bg-amber-100 px-3 py-2 text-xs">ANTHROPIC_API_KEY = sk-ant-...</pre>
          <p className="mt-2 text-amber-700">Les autres pages fonctionnent sans clé — l'IA est un bonus.</p>
        </div>
      )}

      {result && !loading && (
        <div className="mt-5 space-y-4">
          {result.filter && Object.keys(result.filter).length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-500">Critères compris :</span>
              {Object.entries(result.filter).map(([k, v]) => (
                <Badge key={k} tone="accent">{k} = {String(v)}</Badge>
              ))}
            </div>
          )}
          <KpiGrid>
            <Kpi label="Résultats" value={fmtInt(result.kpis.count)} hint="molécules" tone="accent" />
            <Kpi label="Marché cumulé" value={money$(result.kpis.market_sum_usd)} hint="adressable" />
            <Kpi label="Sans fabricant local" value={fmtInt(result.kpis.white_space)} hint="white space" />
            <Kpi label="Croissance médiane" value={fmtGrowth(result.kpis.growth_median)} hint="vs N-1" />
          </KpiGrid>
          <Card><DataTable columns={cols} rows={result.rows} maxHeight={460} /></Card>
        </div>
      )}
    </div>
  );
}
