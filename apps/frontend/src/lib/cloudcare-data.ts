/**
 * Data contract + aggregation helpers for the CloudCare dashboard (Phase
 * 10) — the CloudCare-domain equivalent of the template's
 * src/data/finance-data.ts. Types here match the REAL backend documents
 * exactly (packages/schemas/schemas.py, services/supervisor/service.py's
 * update_fields, apps/api/routers/decision.py's docs.append) — nothing
 * here is invented shape, only aggregated from what those endpoints
 * actually return.
 */

import { isNum, safeDiv } from "@/lib/format";

// ---------------------------------------------------------------------------
// Proposals — GET /v1/approvals?status= (empty string = every status)
// ---------------------------------------------------------------------------

export type ProposalStatus =
  | "proposed"
  | "pending_approval"
  | "approved"
  | "rejected"
  | "blocked"
  | "executed"
  | "verified";

export type RiskLevel = "low" | "medium" | "high" | "critical";
export type Environment = "development" | "staging" | "production" | "unknown";
export type PolicyOutcome = "auto_approved" | "needs_approval" | "blocked";

/**
 * Matches packages/schemas/schemas.py's Evidence exactly — metric, value,
 * window_days, nothing else. An earlier draft of this type invented `unit`
 * and `source_focus_column` fields the backend never sends; that rendered
 * the literal string "undefined" in VariancePanel. `metric` (e.g.
 * "cpu_p95", "unattached_hours") is the only real provenance a given
 * evidence row carries — there is no separate FOCUS-column reference on
 * the wire.
 */
export interface EvidenceItem {
  metric: string;
  value: number;
  window_days: number;
}

export interface Proposal {
  proposal_id: string;
  tenant_id: string;
  resource_arn: string;
  action_type: string;
  template_id: string;
  parameters: Record<string, unknown>;
  expected_monthly_savings: string;
  risk_level: RiskLevel;
  confidence: number;
  evidence: EvidenceItem[];
  rollback_plan: Record<string, unknown> | null;
  requires_human_approval: boolean;
  status: ProposalStatus;
  environment: Environment;
  rationale: string;
  rationale_plain_english?: string | null;
  business_impact?: string | null;
  risk_notes?: string | null;
  policy_outcome?: PolicyOutcome;
  confidence_score?: number;
  risk_score?: number;
  cost_current_monthly?: string;
  cost_optimized_monthly?: string;
  savings_annual?: string;
  approved_at?: string | null;
  approved_by?: string | null;
  rejected_at?: string | null;
  rejected_by?: string | null;
  rejection_reason?: string | null;
}

export type Provider = "aws" | "azure" | "gcp" | "vps" | "unknown";

/** resource_arn's own format is the only real signal — no proposal
 * document carries a provider field (see services/supervisor/service.py;
 * it's never persisted, only read as a fallback default). Derived, not
 * fabricated: an AWS ARN, an Azure resource id, or a bare VPS host all
 * have recognizably different shapes. */
export function deriveProvider(resourceArn: string): Provider {
  if (!resourceArn) return "unknown";
  if (resourceArn.startsWith("arn:aws:")) return "aws";
  if (resourceArn.toLowerCase().includes("/subscriptions/")) return "azure";
  if (resourceArn.startsWith("vps:") || resourceArn.includes("on-premises")) return "vps";
  return "unknown";
}

/** template_id (ec2.stop.v1, ebs.delete.v1, ...) is the only reliable
 * service signal on a proposal — there is no FOCUS ServiceName join here. */
export function deriveServiceLabel(templateId: string): string {
  if (templateId.startsWith("ec2.")) return "EC2";
  if (templateId.startsWith("ebs.")) return "EBS";
  const [prefix] = templateId.split(".");
  return prefix ? prefix.toUpperCase() : "—";
}

export function resourceIdFromArn(resourceArn: string): string {
  const idx = resourceArn.lastIndexOf("/");
  return idx >= 0 ? resourceArn.slice(idx + 1) : resourceArn;
}

const OPEN_SAVINGS_STATUSES = new Set<ProposalStatus>(["pending_approval", "approved"]);

/** Sum of expected_monthly_savings across approved + pending proposals —
 * item 1's "Projected monthly savings" KPI. Rejected/blocked/executed
 * proposals don't count: rejected and blocked will never happen, executed
 * has already happened (it's baked into current spend, not a projection). */
export function projectedMonthlySavings(proposals: Proposal[]): number {
  return proposals
    .filter((p) => OPEN_SAVINGS_STATUSES.has(p.status))
    .reduce((sum, p) => sum + (Number(p.expected_monthly_savings) || 0), 0);
}

export function pendingApprovalsCount(proposals: Proposal[]): number {
  return proposals.filter((p) => p.status === "pending_approval").length;
}

// ---------------------------------------------------------------------------
// Waterfall — item 4: current monthly cost -> one step per proposal ->
// optimized monthly cost. Only proposals that reached a real decision
// (pending_approval / approved / rejected) participate — "blocked" never
// had a real cost/savings figure attached, "proposed" hasn't been scored
// by the Supervisor yet, "executed"/"verified" are already reflected in
// current spend, not a future transition.
// ---------------------------------------------------------------------------

export interface WaterfallStep {
  key: string;
  label: string;
  /** signed impact on monthly cost — negative is a saving */
  impact: number;
  start: number;
  end: number;
  kind: "anchor" | "delta";
  proposal?: Proposal;
}

const WATERFALL_STATUSES = new Set<ProposalStatus>(["pending_approval", "approved", "rejected"]);

export function buildCostWaterfall(proposals: Proposal[]): WaterfallStep[] {
  const included = proposals.filter((p) => WATERFALL_STATUSES.has(p.status));
  const currentTotal = included.reduce((sum, p) => sum + (Number(p.cost_current_monthly) || 0), 0);

  const steps: WaterfallStep[] = [
    { key: "current", label: "Current monthly cost", impact: currentTotal, start: 0, end: currentTotal, kind: "anchor" },
  ];

  let cursor = currentTotal;
  for (const p of included) {
    // A rejected proposal never actually reduces cost — its step is
    // informational (shown greyed, per the prompt), not applied to the
    // running total, so the closing bar reflects only what actually will
    // (or already did) happen.
    const savings = p.status === "rejected" ? 0 : Number(p.expected_monthly_savings) || 0;
    const impact = -savings;
    steps.push({
      key: p.proposal_id,
      label: `${p.action_type.replace(/_/g, " ")} — ${resourceIdFromArn(p.resource_arn)}`,
      impact,
      start: cursor,
      end: cursor + impact,
      kind: "delta",
      proposal: p,
    });
    cursor += impact;
  }

  steps.push({ key: "optimized", label: "Optimized monthly cost", impact: cursor, start: 0, end: cursor, kind: "anchor" });
  return steps;
}

export function waterfallStepColor(step: WaterfallStep): string {
  if (step.kind === "anchor") return "var(--signal-soft)";
  const status = step.proposal?.status;
  if (status === "approved") return "var(--mint)";
  if (status === "rejected") return "var(--graphite)";
  return "var(--signal)"; // pending_approval
}

// ---------------------------------------------------------------------------
// Sankey — item 2: Provider -> ServiceCategory -> ServiceName -> Environment
// ---------------------------------------------------------------------------

export interface CostFlowRecord {
  ProviderName: string;
  ServiceCategory: string;
  ServiceName: string;
  environment: Environment;
  BilledCost: number;
}

/** Built from proposals (each carries a resource, a derived provider/
 * service, an environment, and a real current-cost figure) rather than
 * raw FOCUS records — the dashboard has no bulk FOCUS-record endpoint,
 * and every resource with real cost data flowing into this dashboard
 * already has a proposal. Documented here as the deliberate scope this
 * phase settled for; a full account-wide flow (every resource, not just
 * flagged ones) would need a new bulk FOCUS endpoint. */
export function costFlowFromProposals(proposals: Proposal[]): CostFlowRecord[] {
  return proposals
    .filter((p) => isNum(Number(p.cost_current_monthly)) && Number(p.cost_current_monthly) > 0)
    .map((p) => ({
      ProviderName: deriveProvider(p.resource_arn).toUpperCase(),
      ServiceCategory: deriveServiceLabel(p.template_id),
      ServiceName: p.template_id,
      environment: p.environment,
      BilledCost: Number(p.cost_current_monthly),
    }));
}

// ---------------------------------------------------------------------------
// Forecast — item 3: GET /v1/forecasts
// ---------------------------------------------------------------------------

export interface ForecastPoint {
  date: string;
  actual: number | null;
  predicted: number | null;
}

// ---------------------------------------------------------------------------
// Cost summary — GET /v1/focus/cost-summary (Phase 10 addition)
// ---------------------------------------------------------------------------

export interface CostSummary {
  period_days: number;
  total_cost_usd: number | null;
  prior_total_cost_usd: number | null;
  resource_count: number;
  message?: string;
}

/** Percent change, or null when there is no comparable prior figure —
 * never a fabricated 100%/0% from a missing denominator. */
export function costDeltaPct(summary: CostSummary | undefined): number | null {
  if (!summary || !isNum(summary.total_cost_usd) || !isNum(summary.prior_total_cost_usd)) return null;
  const r = safeDiv(summary.total_cost_usd - summary.prior_total_cost_usd, Math.abs(summary.prior_total_cost_usd));
  return r === null ? null : r * 100;
}

// ---------------------------------------------------------------------------
// Agent activity — GET /v1/agent-activity
// ---------------------------------------------------------------------------

export type AgentName = "Monitor" | "Analyzer" | "Decision" | "Supervisor" | "Executor";

export interface AgentActivityEntry {
  id: string;
  agent: AgentName;
  message: string;
  timestamp: string;
  status: "success" | "failed";
  duration_ms: number;
  payload: Record<string, unknown>;
}
