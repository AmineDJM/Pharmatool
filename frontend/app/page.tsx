"use client";

import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { fmtMoney, fmtInt, fmtGrowth, fmtPct, growthTone } from "@/lib/format";
import { Hero } from "@/components/Hero";
import { BarList } from "@/components/BarList";
import { Card, Kpi, KpiGrid, Section, Spinner, ErrorState, Badge } from "@/components/ui";

export default function DashboardPage() {
  const { data, error, loading } = useAsync(() => Promise.all([api.overview(), api.meta()]), []);

  const ov = data?.[0];
  const meta = data?.[1];
  const k = ov?.kpis;

  const classBars = (rows: any[]) =>
    (rows ?? []).slice(0, 12).map((c: any) => ({
      label: c.THERAPEUTIC_CLASS,
      value: c.Value_DZD,
      display: fmtMoney(c.Value_DZD, "DZD"),
    }));
  const labBars = (rows: any[]) =>
    (rows ?? []).slice(0, 12).map((l: any) => ({
      label: l.LABORATOIRE,
      value: l.Value_DZD,
      display: fmtMoney(l.Value_DZD, "DZD"),
    }));

  return (
    <div>
      <Hero
        badge={meta ? `📈 Marché ${meta.iqvia_year ?? ""} · IQVIA ville + PCH hôpital` : "📈 Vue d'ensemble"}
        title="Marché pharmaceutique algérien"
        subtitle="Marché total = ville (IQVIA) + hospitalier (PCH) : taille, répartition par canal, classes thérapeutiques et laboratoires leaders, momentum de croissance."
      />

      {loading && <Spinner label="Chargement du marché…" />}
      {error && <ErrorState message={error} />}

      {k && (
        <>
          <KpiGrid>
            <Kpi label="Marché total" value={fmtMoney(k.value_dzd, "DZD")} hint={`≈ ${fmtMoney(k.value_usd, "$")} · ville + hôpital`} tone="accent" />
            <Kpi label="Marché ville (IQVIA)" value={fmtMoney(k.ville_dzd, "DZD")} hint={`${fmtPct(k.ville_share, 0)} du total`} />
            <Kpi label="Marché hôpital (PCH)" value={fmtMoney(k.hosp_dzd, "DZD")} hint={`${fmtPct(k.hosp_share, 0)} du total`} />
            <Kpi label="Croissance ville vs N-1" value={fmtGrowth(k.growth_py)} hint="valeur, IQVIA" tone={growthTone(k.growth_py)} />
          </KpiGrid>

          <p className="mt-3 text-xs text-slate-400">
            Ville {fmtInt(k.n_labs_ville)} laboratoires · Hôpital {fmtInt(k.n_labs_hosp)} fournisseurs · Concentration ville {k.hhi_label} (HHI {fmtInt(k.hhi)}).
            Les classes et laboratoires sont présentés par canal (les nomenclatures IQVIA et PCH diffèrent).
          </p>

          <div className="mt-6 grid gap-5 lg:grid-cols-2">
            <Card>
              <Section title="Top classes — marché ville" subtitle="IQVIA, par valeur (ATC4)." right={<Badge tone="accent">🏙️ Ville</Badge>} />
              <BarList items={classBars(ov.classes)} />
            </Card>

            <Card>
              <Section title="Top classes — marché hôpital" subtitle="PCH, par valeur (domaines hospitaliers)." right={<Badge tone="muted">🏥 Hôpital</Badge>} />
              <BarList items={classBars(ov.pch_classes)} />
            </Card>

            <Card>
              <Section title="Laboratoires leaders — ville" subtitle="Classement officiel IQVIA par valeur." right={<Badge tone="accent">🏙️ Ville</Badge>} />
              <BarList items={labBars(ov.labs)} />
            </Card>

            <Card>
              <Section title="Fournisseurs leaders — hôpital" subtitle="PCH, par valeur des réceptions." right={<Badge tone="muted">🏥 Hôpital</Badge>} />
              <BarList items={labBars(ov.pch_labs)} />
            </Card>

            <Card>
              <Section title="Momentum positif" subtitle="Classes ville en plus forte croissance." right={<Badge tone="good">🟢 Croissance</Badge>} />
              <BarList
                items={(ov.growers ?? []).slice(0, 10).map((c: any) => ({
                  label: c.THERAPEUTIC_CLASS,
                  value: c.Growth_PY,
                  display: fmtGrowth(c.Growth_PY),
                  tone: "good" as const,
                }))}
              />
            </Card>

            <Card>
              <Section title="En recul" subtitle="Classes ville en plus fort déclin." right={<Badge tone="bad">🔴 Déclin</Badge>} />
              <BarList
                items={(ov.decliners ?? []).slice(0, 10).map((c: any) => ({
                  label: c.THERAPEUTIC_CLASS,
                  value: c.Growth_PY,
                  display: fmtGrowth(c.Growth_PY),
                  tone: "bad" as const,
                }))}
              />
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
