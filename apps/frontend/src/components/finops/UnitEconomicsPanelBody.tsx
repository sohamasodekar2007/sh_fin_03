"use client";

import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Money } from "@/components/Money";
import { fmtPct } from "@/lib/format";
import type { MarginResult, UnitEconomicsSummary } from "@/lib/finops-api";

function marginColor(pct: number): string {
  if (pct < 0) return "var(--destructive)";
  if (pct < 40) return "#d97706";
  return "var(--mint)";
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: MarginResult }[] }) {
  if (!active || !payload?.length) return null;
  const m = payload[0].payload;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-[12px]"
      style={{ background: "var(--surface)", borderColor: "var(--hairline)" }}
    >
      <p className="num text-foreground mb-1">{m.scope}</p>
      <p className="text-ink-faint">
        <Money value={m.revenue} inline usdOnly /> rev · <Money value={m.cost} inline usdOnly /> cost
      </p>
      <p style={{ color: marginColor(m.gross_margin_pct) }}>{fmtPct(m.gross_margin_pct / 100)} margin</p>
    </div>
  );
}

export function UnitEconomicsPanelBody({ summary }: { summary: UnitEconomicsSummary }) {
  return (
    <div>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={summary.all_margins} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <XAxis
              dataKey="scope"
              tick={{ fontSize: 10.5, fill: "var(--ink-faint)" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: string) => v.replace("merchant-", "")}
            />
            <YAxis tick={{ fontSize: 10.5, fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} width={36} />
            <ReferenceLine y={0} stroke="var(--hairline)" />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--accent)" }} />
            <Bar dataKey="gross_margin_pct" radius={[4, 4, 0, 0]}>
              {summary.all_margins.map((m) => (
                <Cell key={m.scope} fill={marginColor(m.gross_margin_pct)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {summary.negative_margins.length > 0 && (
        <div className="mt-2 border-t border-hairline pt-3">
          <p className="eyebrow mb-1.5" style={{ color: "var(--destructive)" }}>
            {summary.negative_margins.length} scope(s) below margin floor
          </p>
          {summary.negative_margins.map((m) => (
            <p key={m.scope} className="mb-1 text-[11px] leading-relaxed text-ink-faint">
              {m.rationale}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
