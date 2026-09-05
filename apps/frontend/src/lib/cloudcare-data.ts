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
  | "queued_for_execution"
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
  created_at?: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
  rejected_at?: string | null;
  rejected_by?: string | null;
  rejection_reason?: string | null;
  execution_id?: string | null;
  execution_status?: string | null;
  execution_mode?: "simulation" | "live" | null;
  execution_reason_codes?: string[];
  execution_before_state?: Record<string, unknown>;
  execution_after_state?: Record<string, unknown>;
  execution_rollback_descriptor?: Record<string, unknown> | null;
  actual_aws_call_made?: boolean;
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

// ---------------------------------------------------------------------------
// Resources — GET /v1/resources (packages/schemas/schemas.py's Resource).
// The full monitored inventory, independent of whether a resource has a
// proposal — this is what makes every real resource visible, not just
// flagged ones.
// ---------------------------------------------------------------------------

export type ResourceStatus = "Healthy" | "Idle" | "Over-provisioned" | "At-risk";

export interface ResourceItem {
  id: string;
  type: string;
  region: string;
  cpu_p95: number;
  status: ResourceStatus;
  /** null when this resource has no real FOCUS BilledCost yet — never a
   * fabricated flat guess. See apps/api/routers/observation.py's
   * resource-sync step. */
  monthly_cost_usd: number | null;
  cost_source: "focus_live_export" | "focus_synthesized" | "focus_sample" | "focus_modelled" | "no_focus_row";
  focus_dataset_id: string | null;
  focus_version: string | null;
  focus_source: string | null;
  focus_row_count: number;
  resource_type: string | null;
  provider: string | null;
  state: string | null;
  tags: Record<string, string>;
  owner: string | null;
  environment: "dev" | "staging" | "prod";
}

// ---------------------------------------------------------------------------
// Resource detail — GET /v1/resources/{resource_id} (apps/api/routers/
// resources.py's ResourceDetail). Everything known about one resource:
// the FOCUS cost rows that actually reference it (not just the single
// monthly_cost_usd figure ResourceItem carries), its CloudWatch-derived
// utilization metric if collected, and any proposal whose resource_arn
// ends in this id.
// ---------------------------------------------------------------------------

export interface ResourceCostPoint {
  date: string;
  billed_cost: number;
}

export interface ResourceChargeBreakdownItem {
  charge_description: string;
  charge_category: string;
  billed_cost: number;
  row_count: number;
}

export interface ResourceUtilizationMetric {
  metric_id: string;
  resource_id: string;
  tenant_id: string;
  window_start: string;
  window_end: string;
  cpu_p95: number | null;
  cpu_avg: number | null;
  mem_p95: number | null;
  network_p95_bytes: number | null;
  sample_count: number;
}

export interface ResourceDetail {
  resource: ResourceItem;
  metric: ResourceUtilizationMetric | null;
  cost_trend: ResourceCostPoint[];
  charge_breakdown: ResourceChargeBreakdownItem[];
  focus_dataset_id: string | null;
  focus_row_count: number;
  related_proposals: Proposal[];
}

// ---------------------------------------------------------------------------
// Connected accounts — GET /v1/cloud-accounts (ConnectedAccountSummary in
// apps/api/routers/accounts_runs.py). Deliberately slim — no secret fields
// exist on this contract at all, unlike the full CloudAccount model.
// ---------------------------------------------------------------------------

export interface ConnectedAccount {
  provider: string;
  account_id: string;
  region: string;
  connected: boolean;
  status: "pending" | "validated" | "failed";
}

// ---------------------------------------------------------------------------
// Chat (CloudCareAI) — packages/schemas/chat.py. Field names confirmed by
// direct read, not guessed; the old apps/web chat UI targeted a different,
// now-nonexistent endpoint shape and was not reusable.
// ---------------------------------------------------------------------------

export type ChatRole = "system" | "user" | "assistant" | "tool";

export interface ChatMessage {
  role: ChatRole;
  content: string;
  tool_call_id?: string | null;
  name?: string | null;
  created_at: string;
}

export interface ApprovalCard {
  type: "approval_card";
  proposal_id: string;
  action: string;
  target: string;
  savings: number;
  risk: string;
  confidence: number;
}

export interface FindingCard {
  type: "finding_card";
  resource_id: string;
  rule_id: string;
  summary: string;
  evidence: Record<string, unknown>;
}

export interface CostSummaryCard {
  type: "cost_summary_card";
  period_days: number;
  total_cost_usd: number;
  top_services: Array<{ service_name?: string; cost_usd?: number } & Record<string, unknown>>;
}

export interface RecommendationOption {
  name: string;
  estimated_monthly_cost_usd: number;
  pros: string[];
  cons: string[];
}

export interface RecommendationCard {
  type: "recommendation_card";
  summary: string;
  estimated_monthly_cost_usd: number;
  reasoning: string;
  options: RecommendationOption[];
}

export type ChatCard = ApprovalCard | FindingCard | CostSummaryCard | RecommendationCard;

export interface ChatSessionCreateResponse {
  session_id: string;
}

export interface ChatHistoryResponse {
  session_id: string;
  messages: ChatMessage[];
}

export interface ChatMessageResponse {
  session_id: string;
  role: "assistant";
  content: string;
  cards: ChatCard[];
  tool_calls_made: string[];
}

// ---------------------------------------------------------------------------
// IAM & Governance — GET /v1/governance/iam-overview
// (packages/schemas/governance.py). Account-wide identity/access structure
// plus a CloudTrail-derived audit trail — a different shape from
// ResourceItem, not an extension of it.
// ---------------------------------------------------------------------------

export interface AccountOverview {
  account_id: string;
  alias: string | null;
  /** null (not false) when get_account_summary itself couldn't be read —
   * "unknown" must never render as "MFA disabled." */
  root_mfa_enabled: boolean | null;
  root_access_keys_present: boolean | null;
  password_policy_configured: boolean | null;
}

export interface IAMPolicyRef {
  name: string;
  arn: string | null;
  type: "managed" | "inline";
  /** Only ever populated for inline policies. */
  document: Record<string, unknown> | null;
}

export interface IAMUserDetail {
  user_name: string;
  arn: string;
  created_at: string | null;
  groups: string[];
  policies: IAMPolicyRef[];
  /** null when no active access key exists at all. */
  access_key_age_days: number | null;
}

export interface ResourceCreator {
  resource_id: string;
  event_name: string;
  principal_arn: string | null;
  principal_name: string | null;
  event_time: string;
}

export interface IAMGovernanceOverview {
  account: AccountOverview;
  users: IAMUserDetail[];
  resource_creators: ResourceCreator[];
  resource_creators_lookback_days: number;
  /** Keyed by section ("account" | "users" | "resource_creators") — set
   * when that section couldn't be collected at all (e.g. AccessDenied),
   * so the page can say why instead of just showing empty. */
  errors: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Parquet analysis - GET /v1/parquet-analysis
// ---------------------------------------------------------------------------

export interface ParquetColumn {
  name: string;
  type: string;
  nullable: boolean;
}

export interface ParquetBreakdownItem {
  name: string;
  cost_usd: number;
  rows: number;
}

export interface ParquetAnalysis {
  file: {
    source: "s3";
    uri: string;
    bucket: string;
    key: string;
    name: string;
    size_bytes: number;
    compression: string;
    last_modified: string;
  };
  summary: {
    tenant_id: string;
    rows: number;
    columns: number;
    row_groups: number;
    distinct_resources: number;
    distinct_services: number;
    billed_cost_usd: number;
    effective_cost_usd: number;
    list_cost_usd: number;
    savings_vs_list_usd: number;
  };
  schema: ParquetColumn[];
  breakdowns: {
    by_service: ParquetBreakdownItem[];
    by_category: ParquetBreakdownItem[];
    by_region: ParquetBreakdownItem[];
    by_charge_category: ParquetBreakdownItem[];
  };
  sample_rows: Array<Record<string, unknown>>;
  converter: {
    cadence_minutes: number;
    scheduler_interval_minutes: number;
    parquet_analysis_interval_minutes?: number;
    s3_configured: boolean;
    bucket: string | null;
    prefix: string;
    target_key: string;
    target_uri: string | null;
    formats: string[];
    compression: string;
    mode: string;
  };
  generated_at: string;
}

export interface ParquetRewriteResult {
  status: "rewritten";
  message?: string;
  source_uri?: string;
  target_uri?: string;
  rewritten_at?: string;
  plan: ParquetAnalysis["converter"];
}

// ---------------------------------------------------------------------------
// Phase 14 — Multi-Service Awareness (services/phase14/schemas.py). These
// are deliberately NOT Proposal — RDS/S3 recommendations and IAM security
// findings never enter the real approve/execute pipeline, so they get
// their own disjoint types with no shared shape to accidentally reuse.
// ---------------------------------------------------------------------------

export interface SecurityFinding {
  finding_id: string;
  rule_id: string;
  severity: "low" | "medium" | "high" | "critical";
  principal_type: "user" | "role";
  principal_name: string;
  principal_arn: string | null;
  policy_name: string;
  policy_type: "managed" | "inline";
  summary: string;
  evidence: Record<string, unknown>;
  detected_at: string;
}

export interface RDSRecommendation {
  resource_id: string;
  db_instance_class: string;
  region: string;
  environment: string;
  finding: "idle_candidate";
  confidence: number;
  current_monthly_cost: number | null;
  evidence: Record<string, unknown>;
  rationale: string;
  requires_human_approval: true;
}

export interface S3Recommendation {
  bucket: string;
  region: string;
  current_storage_class: string;
  suggested_storage_class: string;
  evidence: Record<string, unknown>;
  rationale: string;
  requires_human_approval: true;
}

export interface RDSRecommendationsResponse {
  recommendations: RDSRecommendation[];
  enabled: boolean;
  error: string | null;
}

export interface S3RecommendationsResponse {
  recommendations: S3Recommendation[];
  enabled: boolean;
  error: string | null;
}

export interface SecurityFindingsResponse {
  findings: SecurityFinding[];
  enabled: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// AWS Core Services external factor - GET /v1/external-factors/aws-core-services
// Detached service/rule/policy metadata. It is intentionally not part of the
// executor contract and performs no AWS mutation.
// ---------------------------------------------------------------------------

export interface AwsCoreServiceFactor {
  service: string;
  slug: string;
  resource_types: string[];
  purpose: string;
  inventory_status: "implemented" | "planned";
  collector_actions: string[];
  read_only_policies: string[];
  full_access_policies: string[];
  approved_executor_actions: string[];
  blocked_executor_actions: string[];
  rules: string[];
  risk_notes: string;
}

export interface AwsCoreServicesExternalFactor {
  generated_at: string;
  source: string;
  scope: string;
  services: AwsCoreServiceFactor[];
  discovery_role_recommendations: string[];
  executor_role_boundaries: {
    allowed_pattern: string;
    excluded: string[];
    required_gates: string[];
  };
  notes: string[];
}
