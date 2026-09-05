"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Money } from "@/components/Money";
import { fmtPct } from "@/lib/format";
import type { TeamAttributionReport, TeamCostSummary } from "@/lib/finops-api";

const TEAM_BAR_COLORS = ["var(--signal)", "var(--mint)", "var(--ember)", "var(--signal-soft)", "var(--signal-deep)"];

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: TeamCostSummary }[] }) {
  if (!active || !payload?.length) return null;
  const t = payload[0].payload;
  return (
    <div className="rounded-lg border px-3 py-2 text-[12px]" style={{ background: "var(--surface)", borderColor: "var(--hairline)" }}>
      <p className="num text-foreground mb-1">{t.team}</p>
      <p className="text-ink-faint">
        {t.resource_count} resource{t.resource_count === 1 ? "" : "s"} · {t.environments.join(", ") || "no environment tag"}
      </p>
      <p className="text-foreground">
        <Money value={t.total_monthly_cost} inline usdOnly />
      </p>
    </div>
  );
}

export function TeamAttributionPanelBody({ report }: { report: TeamAttributionReport }) {
  return (
    <div>
      <div style={{ height: Math.max(120, report.teams.length * 34) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={report.teams} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="team" width={84} tick={{ fontSize: 11, fill: "var(--ink-dim)" }} axisLine={false} tickLine={false} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--accent)" }} />
            <Bar dataKey="total_monthly_cost" radius={[0, 4, 4, 0]}>
              {report.teams.map((t, i) => (
                <Cell key={t.team} fill={TEAM_BAR_COLORS[i % TEAM_BAR_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {report.untagged_resources.length > 0 && (
        <div className="mt-3 border-t border-hairline pt-3">
          <p className="eyebrow mb-1.5" style={{ color: "var(--ember)" }}>
            {report.untagged_resources.length} untagged resource{report.untagged_resources.length === 1 ? "" : "s"} ·{" "}
            <Money value={report.untagged_cost} inline usdOnly /> ({fmtPct(report.untagged_pct / 100)} of spend)
          </p>
          <ul className="space-y-0.5">
            {report.untagged_resources.map((r) => (
              <li key={r.resource_id} className="text-[11px] text-ink-faint">
                <span className="num text-ink-dim">{r.resource_id}</span> ({r.resource_type}
                {r.environment ? `, ${r.environment}` : ""}) — <Money value={r.monthly_cost} inline usdOnly />
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-3 border-t border-hairline pt-2 text-[11px] leading-relaxed text-ink-faint">{report.rationale}</p>
    </div>
  );
}
