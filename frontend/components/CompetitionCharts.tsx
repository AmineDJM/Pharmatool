"use client";

import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtGrowth, fmtMoney } from "@/lib/format";

export type Competitor = { LABORATOIRE: string; Value_DZD: number; Share: number; Growth_PY: number | null; Volume?: number };

const COLORS = ["#0d9488", "#10b981", "#0ea5e9", "#6366f1", "#14b8a6", "#f59e0b", "#a855f7", "#34d399", "#f43f5e", "#64748b"];

function trunc(s: string, n = 18) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

export function ShareDonut({ data }: { data: Competitor[] }) {
  const top = data.slice(0, 9).map((d) => ({ name: d.LABORATOIRE, value: d.Value_DZD || 0 }));
  const restVal = data.slice(9).reduce((s, d) => s + (d.Value_DZD || 0), 0);
  const pie = restVal > 0 ? [...top, { name: "Autres", value: restVal }] : top;
  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie data={pie} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={62} outerRadius={104} paddingAngle={1}>
          {pie.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="#fff" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip formatter={(v: any, n: any) => [fmtMoney(Number(v), "DZD"), n]} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function GrowthBars({ data }: { data: Competitor[] }) {
  const rows = data
    .slice(0, 10)
    .map((d) => ({ name: d.LABORATOIRE, g: typeof d.Growth_PY === "number" ? d.Growth_PY : 0 }))
    .sort((a, b) => a.g - b.g);
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 32)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 6, right: 16, top: 4, bottom: 4 }}>
        <XAxis type="number" tickFormatter={(v) => `${Math.round(v * 100)}%`} fontSize={11} stroke="#94a3b8" />
        <YAxis type="category" dataKey="name" width={120} fontSize={11} stroke="#94a3b8" tickFormatter={(s: string) => trunc(String(s))} />
        <Tooltip formatter={(v: any) => fmtGrowth(Number(v))} />
        <Bar dataKey="g" radius={[0, 4, 4, 0]}>
          {rows.map((r, i) => (
            <Cell key={i} fill={r.g >= 0 ? "#10b981" : "#f43f5e"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
