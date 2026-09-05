"use client";

import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Money, formatMoneyParts } from "@/components/Money";
import type { ForecastComparison } from "@/lib/finops-api";

const SEVERITY_COLOR: Record<string, string> = {
  normal: "var(--mint)",
  watch: "var(--signal)",
  warning: "var(--ember)",
  critical: "var(--destructive)",
};

export function ForecastAnomalyPanelBody({ comparisons }: { comparisons: ForecastComparison[] }) {
  if (comparisons.length === 0) {
    return <p className="py-8 text-center text-[12.5px] text-ink-faint">Not enough history to evaluate yet.</p>;
  }

  const latest = comparisons[comparisons.length - 1];
  const color = SEVERITY_COLOR[latest.severity] ?? "var(--ink-faint)";

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline gap-5">
        <div>
          <p className="eyebrow">latest actual</p>
          <Money value={latest.actual_cost} className="text-[15px]" style={{ color }} />
        </div>
        <div>
          <p className="eyebrow">predicted</p>
          <Money value={latest.predicted_cost} className="text-[15px]" style={{ color: "var(--ink-dim)" }} />
        </div>
        <div>
          <p className="eyebrow">overage</p>
          <p className="num text-[15px]" style={{ color }}>
            {latest.overage_pct >= 0 ? "+" : ""}
            {latest.overage_pct.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="mb-2 h-40">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={comparisons} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} tickFormatter={(d: string) => d.slice(5)} />
            <YAxis tick={{ fontSize: 10, fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} width={40} />
            <ReferenceLine y={0} stroke="var(--hairline)" />
            <Tooltip
              formatter={(value: number, name: string) => [formatMoneyParts(value).usd, name]}
              labelFormatter={(label) => `${label}`}
              contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "var(--hairline)", background: "var(--surface)" }}
            />
            <Line type="monotone" dataKey="predicted_cost" name="predicted" stroke="var(--ink-faint)" strokeDasharray="4 3" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="actual_cost" name="actual" stroke={color} strokeWidth={2} dot={{ r: 2.5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="border-t border-hairline pt-2 text-[11px] leading-relaxed text-ink-faint">{latest.rationale}</p>
    </div>
  );
}
