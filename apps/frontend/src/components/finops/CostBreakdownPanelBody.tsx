"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Money } from "@/components/Money";
import { fmtPct } from "@/lib/format";
import type { CostBreakdown, CostContributor } from "@/lib/finops-api";

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: CostContributor }[] }) {
  if (!active || !payload?.length) return null;
  const c = payload[0].payload;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-[12px]"
      style={{ background: "var(--surface)", borderColor: "var(--hairline)" }}
    >
      <p className="num text-foreground mb-1">{c.dimension_value}</p>
      <p className="text-ink-faint">
        <Money value={c.baseline_cost} inline usdOnly /> → <Money value={c.current_cost} inline usdOnly />
      </p>
      <p style={{ color: c.delta >= 0 ? "var(--destructive)" : "var(--mint)" }}>
        <Money value={c.delta} inline usdOnly /> ({fmtPct(c.pct_of_total_delta / 100)})
      </p>
    </div>
  );
}

export function CostBreakdownPanelBody({ breakdown }: { breakdown: CostBreakdown }) {
  const chartData = [...breakdown.contributors].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  return (
    <div>
      <p className="mb-3 text-[12.5px] text-foreground">
        Delta of <Money value={breakdown.total_delta} inline usdOnly /> on{" "}
        <span className="text-ink-faint">{breakdown.scope}</span>, by{" "}
        <span className="text-ink-faint">{breakdown.dimension_key}</span>
      </p>

      <div style={{ height: Math.max(120, chartData.length * 34) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="dimension_value"
              width={72}
              tick={{ fontSize: 11, fill: "var(--ink-dim)" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--accent)" }} />
            <Bar dataKey="delta" radius={[0, 4, 4, 0]}>
              {chartData.map((c) => (
                <Cell key={c.dimension_value} fill={c.delta >= 0 ? "var(--destructive)" : "var(--mint)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {breakdown.unattributed_pct !== 0 && (
        <p className="mt-1 text-[11.5px] text-ink-faint">
          {fmtPct(breakdown.unattributed_pct / 100)} unattributed to the contributors shown above.
        </p>
      )}
      <p className="mt-3 border-t border-hairline pt-2 text-[11px] leading-relaxed text-ink-faint">
        {breakdown.rationale}
      </p>
    </div>
  );
}
