"use client";

import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { fmtMoney, fmtInt, fmtGrowth, growthTone } from "@/lib/format";
import { Hero } from "@/components/Hero";
import { BarList } from "@/components/BarList";
import { Card, Kpi, KpiGrid, Section, Spinner, ErrorState, Badge } from "@/components/ui";

export default function DashboardPage() {
  const { data, error, loading } = useAsync(() => Promise.all([api.overview(), api.meta()]), []);

  const ov = data?.[0];
  const meta = data?.[1];
  const k = ov?.kpis;

  return (
    <div>
      <Hero
        badge={meta ? `📈 Marché ${meta.iqvia_year ?? ""} · ${meta.iqvia_file ?? "IQVIA"}` : "📈 Vue d'ensemble"}
        title="Marché pharmaceutique algérien"
        subtitle="Vue d'ensemble du marché de ville IQVIA : taille, croissance, classes thérapeutiques porteuses, laboratoires leaders et intensité concurrentielle."
      />

      {loading && <Spinner label="Chargement du marché…" />}
      {error && <ErrorState message={error} />}

      {k && (
        <>
          <KpiGrid>
            <Kpi label="Marché total" value={fmtMoney(k.value_dzd, "DZD")} hint={`≈ ${fmtMoney(k.value_usd, "$")}`} tone="accent" />
            <Kpi label="Croissance vs N-1" value={fmtGrowth(k.growth_py)} hint="valeur, MAT" tone={growthTone(k.growth_py)} />
            <Kpi label="Volume" value={fmtMoney(k.volume, "")} hint="boîtes / an" />
            <Kpi label="Laboratoires actifs" value={fmtInt(k.n_labs)} hint={`${k.hhi_label} · HHI ${fmtInt(k.hhi)}`} />
          </KpiGrid>

          <div className="mt-6 grid gap-5 lg:grid-cols-2">
            <Card>
              <Section title="Top classes thérapeutiques" subtitle="Par valeur de marché (ATC4)." />
              <BarList
                items={(ov.classes ?? []).slice(0, 12).map((c: any) => ({
                  label: c.THERAPEUTIC_CLASS,
                  value: c.Value_DZD,
                  display: fmtMoney(c.Value_DZD, "DZD"),
                }))}
              />
            </Card>

            <Card>
              <Section title="Laboratoires leaders" subtitle="Classement officiel IQVIA par valeur." />
              <BarList
                items={(ov.labs ?? []).slice(0, 12).map((l: any) => ({
                  label: l.LABORATOIRE,
                  value: l.Value_DZD,
                  display: fmtMoney(l.Value_DZD, "DZD"),
                }))}
              />
            </Card>

            <Card>
              <Section title="Momentum positif" subtitle="Classes matérielles en plus forte croissance." right={<Badge tone="good">🟢 Croissance</Badge>} />
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
              <Section title="En recul" subtitle="Classes matérielles en plus fort déclin." right={<Badge tone="bad">🔴 Déclin</Badge>} />
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
