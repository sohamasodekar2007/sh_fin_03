"use client";

import { Money } from "@/components/Money";
import { fmtPct } from "@/lib/format";
import type { PillarScore, TrustedServicesReport, TrustScorecard } from "@/lib/finops-api";

const GRADE_COLOR: Record<TrustScorecard["overall_grade"], string> = {
  A: "var(--mint)",
  B: "var(--mint)",
  C: "var(--ember)",
  D: "var(--destructive)",
  F: "var(--destructive)",
};

function scoreColor(score: number): string {
  if (score >= 75) return "var(--mint)";
  if (score >= 40) return "var(--ember)";
  return "var(--destructive)";
}

const PILLAR_LABEL: Record<PillarScore["pillar"], string> = {
  cost_optimization: "Cost Optimization",
  security: "Security",
  fault_tolerance: "Fault Tolerance",
  service_limits: "Service Limits",
};

export function TrustScorecardPanelBody({
  scorecard,
  allowlist,
}: {
  scorecard: TrustScorecard;
  allowlist: TrustedServicesReport;
}) {
  return (
    <div>
      <div className="mb-4 flex items-center gap-4">
        <div
          className="flex size-14 shrink-0 items-center justify-center rounded-full border-2 font-display text-[1.4rem] font-bold"
          style={{ borderColor: GRADE_COLOR[scorecard.overall_grade], color: GRADE_COLOR[scorecard.overall_grade] }}
        >
          {scorecard.overall_grade}
        </div>
        <div>
          <p className="num text-[15px] text-foreground">{scorecard.overall_score.toFixed(1)} / 100</p>
          <p className="text-[11.5px] text-ink-faint">{scorecard.rationale}</p>
        </div>
      </div>

      <div className="mb-4 space-y-2.5">
        {scorecard.pillars.map((p) => (
          <div key={p.pillar}>
            <div className="mb-1 flex items-center justify-between text-[11.5px]">
              <span className="text-ink-dim">{PILLAR_LABEL[p.pillar]}</span>
              <span className="num" style={{ color: scoreColor(p.score) }}>
                {p.score.toFixed(0)}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full" style={{ background: "var(--accent)" }}>
              <div className="h-full rounded-full" style={{ width: `${p.score}%`, background: scoreColor(p.score) }} />
            </div>
          </div>
        ))}
      </div>

      {allowlist.unapproved.length > 0 && (
        <div className="border-t border-hairline pt-3">
          <p className="eyebrow mb-1.5" style={{ color: "var(--ember)" }}>
            {allowlist.unapproved.length} unapproved service{allowlist.unapproved.length === 1 ? "" : "s"} in use ·{" "}
            {fmtPct(allowlist.unapproved_pct / 100)} of tracked spend
          </p>
          <ul className="space-y-0.5">
            {allowlist.unapproved.map((u) => (
              <li key={u.service} className="text-[11px] text-ink-faint">
                <span className="num text-ink-dim">{u.service}</span> — {u.resource_count} resource{u.resource_count === 1 ? "" : "s"},{" "}
                <Money value={u.monthly_cost} inline usdOnly />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
