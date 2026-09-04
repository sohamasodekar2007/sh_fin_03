"use client";

import { AlertTriangle, TrendingUp } from "lucide-react";
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis } from "recharts";

import { Money, formatMoneyParts } from "@/components/Money";
import type { FinopsSeverity, SpendSeriesPoint, VelocityAlert } from "@/lib/finops-api";

const SEVERITY_COLOR: Record<FinopsSeverity, string> = {
  low: "var(--mint)",
  medium: "#d97706",
  high: "#d97706",
  critical: "var(--destructive)",
};

/**
 * Body only — the page owns the Panel wrapper, the query, and the
 * loading/unreachable branching, same split as S3RecommendationsPanel /
 * RDSRecommendationsPanel in components/phase14/.
 */
export function SpendVelocityPanelBody({
  alert,
  series,
}: {
  alert: VelocityAlert | null;
  series: SpendSeriesPoint[];
}) {
  if (alert === null) {
    return (
      <div className="flex items-center gap-2 py-6">
        <TrendingUp className="size-4" style={{ color: "var(--mint)" }} />
        <p className="text-[12.5px] text-ink-dim">No velocity anomalies detected.</p>
      </div>
    );
  }

  const color = SEVERITY_COLOR[alert.severity];
  const baselineAvg =
    series.filter((p) => p.phase === "baseline").reduce((sum, p, _i, arr) => sum + p.cost / arr.length, 0) || 0;

  return (
    <div>
      <div className="mb-2 flex items-baseline gap-2">
        <AlertTriangle className="size-4" style={{ color }} />
        <span className="text-[1.15rem] font-semibold leading-tight" style={{ color }}>
          {alert.severity.toUpperCase()}
        </span>
        <span className="num text-[11.5px] text-ink-faint">{alert.scope}</span>
      </div>

      <div className="mb-3 flex flex-wrap items-baseline gap-5">
        <div>
          <p className="eyebrow">current /hr</p>
          <Money value={alert.reading.current_hourly_rate} className="text-[15px]" />
        </div>
        <div>
          <p className="eyebrow">baseline /hr</p>
          <Money value={alert.reading.baseline_hourly_rate} className="text-[15px]" style={{ color: "var(--ink-dim)" }} />
        </div>
        <div>
          <p className="eyebrow">ratio</p>
          <p className="num text-[15px]" style={{ color }}>
            {alert.reading.velocity_ratio >= 1000 ? "new" : `${alert.reading.velocity_ratio.toFixed(1)}x`}
          </p>
        </div>
      </div>

      {series.length > 0 && (
        <div className="mb-2 -mx-1 h-16">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id="finops-spend-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="label" hide />
              {baselineAvg > 0 && (
                <ReferenceLine y={baselineAvg} stroke="var(--hairline)" strokeDasharray="3 3" strokeWidth={1} />
              )}
              <Tooltip
                formatter={(value: number) => [formatMoneyParts(value).usd, "cost"]}
                labelFormatter={(label) => `${label}`}
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 8,
                  borderColor: "var(--hairline)",
                  background: "var(--surface)",
                }}
              />
              <Area type="monotone" dataKey="cost" stroke={color} strokeWidth={2} fill="url(#finops-spend-fill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <p className="mb-3 text-[11.5px] text-ink-faint">
        Projected 24h impact: <Money value={alert.projected_24h_cost} inline usdOnly className="text-foreground" />
      </p>

      <p className="border-t border-hairline pt-2 text-[11px] leading-relaxed text-ink-faint">{alert.rationale}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="eyebrow">Recommended</span>
        <span className="num text-[11.5px] text-foreground">{alert.recommended_action.replace(/_/g, " ")}</span>
        {alert.requires_human_approval && (
          <span className="rounded-full border border-hairline px-2 py-0.5 text-[10.5px] text-ink-faint">
            needs approval
          </span>
        )}
      </div>
    </div>
  );
}
