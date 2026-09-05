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
  resource_id?: string;
  resource_name?: string | null;
  resource_type?: string | null;
  tags?: Record<string, string>;
  action_type: string;
  template_id: string;
  parameters: Record<string, unknown>;
  expected_monthly_savings: string;
  risk_level: RiskLevel;
  confidence: number;
  evidence: EvidenceItem[];
  dependency_facts?: string[];
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

/** Mirrors services/decision/service.py's _service_for_resource_type —
 * the real originating AWS service for a proposal's resource_type, when
 * that field happens to be populated (real documents from the live
 * pipeline currently leave it null — see serviceSegmentFromArn below for
 * the signal that's actually always present). */
const RESOURCE_TYPE_SERVICE_LABEL: Record<string, string> = {
  ec2_instance: "EC2",
  ebs_volume: "EBS",
  rds_instance: "RDS",
  dynamodb_table: "DynamoDB",
  lambda_function: "Lambda",
  security_group: "Security Groups",
  vpc: "VPC",
  s3_bucket: "S3",
};

const ARN_SERVICE_LABEL: Record<string, string> = {
  ec2: "EC2",
  rds: "RDS",
  dynamodb: "DynamoDB",
  lambda: "Lambda",
  s3: "S3",
};

/** An ARN's own service segment (arn:aws:{service}:region:account:...) —
 * required, always present, and it's exactly what
 * services/decision/service.py's _service_for_resource_type itself wrote
 * in when it built a finding's synthetic ARN. Far more reliable than
 * resource_type, which real documents currently leave null. */
function serviceSegmentFromArn(resourceArn: string): string | null {
  const parts = resourceArn.split(":");
  return parts.length > 2 ? parts[2] : null;
}

/** A synthetic "finding" ARN ends ".../finding/{rule_id}" — the original,
 * specific rule (e.g. "rds.unencrypted.v1", "sg.open_ingress.v1") that
 * services/decision/service.py's _RULE_TO_TEMPLATE flattened down to the
 * one generic "aws.audit_review.v1" template_id. Recovering it from the
 * ARN is the only way to tell 8 different audit findings apart on the
 * dashboard instead of showing "Audit Review" 8 times. */
function findingRuleIdFromArn(resourceArn: string): string | null {
  const match = resourceArn.match(/\/finding\/([^/]+)$/);
  return match ? match[1] : null;
}

/** Prefers `resourceType` when populated, then the ARN's own service
 * segment (see serviceSegmentFromArn), then finally template_id's own
 * prefix. template_id alone can't disambiguate: "aws.audit_review.v1" is
 * one generic template reused for RDS, DynamoDB, Lambda, and Security
 * Group findings alike, which is exactly why a template_id-only fallback
 * used to render the literal string "AWS" as a "service" — duplicating
 * the Provider node one level up in the cost-flow Sankey instead of
 * naming a real service. That fallback here never repeats the bare
 * provider name either, for whatever resource_arn shape it hasn't seen. */
export function deriveServiceLabel(templateId: string, resourceArn: string, resourceType?: string | null): string {
  if (resourceType && RESOURCE_TYPE_SERVICE_LABEL[resourceType]) {
    return RESOURCE_TYPE_SERVICE_LABEL[resourceType];
  }
  const arnService = serviceSegmentFromArn(resourceArn);
  if (arnService && ARN_SERVICE_LABEL[arnService]) {
    return ARN_SERVICE_LABEL[arnService];
  }
  if (templateId.startsWith("ec2.")) return "EC2";
  if (templateId.startsWith("ebs.")) return "EBS";
  const [prefix] = templateId.split(".");
  if (!prefix || prefix.toLowerCase() === "aws") return "Other";
  return prefix.toUpperCase();
}

/** Every specific rule_id (services/decision/service.py's
 * _RULE_TO_TEMPLATE keys) and actionable template_id this repo currently
 * issues maps to a human label here. Falls back to humanizing the raw
 * id — strip the provider prefix and ".vN" suffix, title-case the rest —
 * so an id added later still reads as words instead of a raw dotted slug. */
const ACTION_LABEL_OVERRIDES: Record<string, string> = {
  "ec2.stop.v1": "Stop Instance",
  "ec2.start.v1": "Start Instance",
  "ec2.resize.v1": "Resize Instance",
  "ec2.schedule.v1": "Schedule Off-Hours",
  "ebs.delete.v1": "Delete Volume",
  "aws.audit_review.v1": "Audit Review",
  "rds.unencrypted.v1": "Unencrypted Storage",
  "rds.publicly_accessible.v1": "Publicly Accessible",
  "rds.single_az.v1": "Single-AZ (No Failover)",
  "rds.deletion_protection_disabled.v1": "Deletion Protection Disabled",
  "dynamodb.pitr_disabled.v1": "Point-in-Time Recovery Disabled",
  "lambda.long_timeout.v1": "Long Timeout",
  "lambda.prod_without_vpc.v1": "Production Without VPC",
  "sg.open_ingress.v1": "Open Ingress Rule",
};

function humanizeId(id: string): string {
  const withoutVersion = id.replace(/\.v\d+$/i, "");
  const segments = withoutVersion.split(".").filter(Boolean);
  const withoutPrefix = segments.length > 1 ? segments.slice(1) : segments;
  const words = withoutPrefix.join(" ").split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return id;
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

/** Prefers the specific rule_id recovered from a synthetic finding ARN
 * (see findingRuleIdFromArn) over the proposal's own template_id — that
 * field is flattened to one generic bucket for every audit-review
 * finding, so using it directly would show "Audit Review" for 8
 * different underlying problems. Actionable EC2/EBS proposals have no
 * /finding/ ARN suffix, so they fall through to their own template_id
 * unaffected. */
export function deriveActionLabel(templateId: string, resourceArn?: string): string {
  const effectiveId = (resourceArn && findingRuleIdFromArn(resourceArn)) || templateId;
  return ACTION_LABEL_OVERRIDES[effectiveId] ?? humanizeId(effectiveId);
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

function environmentFromResource(value: ResourceItem["environment"] | null | undefined): Environment {
  if (value === "prod") return "production";
  if (value === "staging") return "staging";
  if (value === "dev") return "development";
  return "unknown";
}

function serviceCategoryFromResource(resource: ResourceItem): string {
  const type = (resource.resource_type ?? resource.type ?? "").toLowerCase();
  if (type.includes("ec2")) return "EC2";
  if (type.includes("ebs")) return "EBS";
  if (type.includes("rds")) return "RDS";
  if (type.includes("dynamodb")) return "DynamoDB";
  if (type.includes("lambda")) return "Lambda";
  if (type.includes("security_group")) return "Security Groups";
  if (type.includes("vpc")) return "VPC";
  if (type.includes("s3")) return "S3";
  return resource.resource_type?.replace(/_/g, " ") || resource.type || "Other";
}

function serviceNameFromResource(resource: ResourceItem): string {
  if (resource.resource_type === "ec2_instance") return resource.instance_type || resource.type || "EC2 instance";
  if (resource.resource_type === "ebs_volume") return resource.type || "EBS volume";
  if (resource.resource_type === "rds_instance") return resource.type || "RDS instance";
  if (resource.resource_type === "lambda_function") return resource.type || "Lambda function";
  if (resource.resource_type === "dynamodb_table") return resource.type || "DynamoDB table";
  if (resource.resource_type === "s3_bucket") return "Bucket";
  return resource.type || resource.resource_type?.replace(/_/g, " ") || "Resource";
}

export function costFlowFromResources(resources: ResourceItem[]): CostFlowRecord[] {
  return resources
    .filter((resource) => isNum(Number(resource.monthly_cost_usd)) && Number(resource.monthly_cost_usd) > 0)
    .map((resource) => ({
      ProviderName: (resource.provider || "aws").toUpperCase(),
      ServiceCategory: serviceCategoryFromResource(resource),
      ServiceName: serviceNameFromResource(resource),
      environment: environmentFromResource(resource.environment),
      BilledCost: Number(resource.monthly_cost_usd),
    }));
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
      ServiceCategory: deriveServiceLabel(p.template_id, p.resource_arn, p.resource_type),
      ServiceName: deriveActionLabel(p.template_id, p.resource_arn),
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
  instance_type?: string | null;
  vcpu?: number | null;
  memory_gib?: number | null;
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
  raw_resource: Record<string, unknown>;
  aws_live_details: Record<string, unknown>;
  aws_live_errors: Record<string, string>;
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
// Chatbot MCP setup - GET/POST /v1/chat/mcp/setup
// ---------------------------------------------------------------------------

export interface ChatMcpTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export interface ChatMcpSetup {
  tenant_id: string;
  enabled: boolean;
  client_name: string;
  allowed_tools: string[];
  instructions: string;
  audit_enabled: boolean;
  created_at: string;
  updated_at: string;
  configured_by: string | null;
}

export interface ChatMcpTokenSummary {
  token_id: string;
  label: string;
  created_at: string;
  created_by: string;
  last_used_at: string | null;
}

export interface ChatMcpAuditEvent {
  tenant_id: string;
  user_id: string;
  method: string;
  tool_name: string | null;
  ok: boolean;
  error: string | null;
  created_at: string;
}

export interface ChatMcpStatus {
  mcp_enabled: boolean;
  env_token_configured: boolean;
  dashboard_tokens: number;
  mongo_audit_events: number;
  model_configured: boolean;
  model: string;
  model_base_url: string;
  allowed_tool_count: number;
  chatbot_only_scope: boolean;
}

export interface ChatMcpSetupResponse {
  setup: ChatMcpSetup;
  available_tools: ChatMcpTool[];
  tokens: ChatMcpTokenSummary[];
  audit: ChatMcpAuditEvent[];
  status: ChatMcpStatus;
  token?: string;
  token_id?: string;
}

export interface ChatMcpCheck {
  key: string;
  ok: boolean;
  detail: string;
}

export interface ChatMcpCheckResponse {
  checked_at: string;
  checks: ChatMcpCheck[];
  ai_review: {
    ready: boolean;
    summary: string;
    next_actions: string[];
  } | null;
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
    source: "s3" | "local";
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
    by_billing_account?: ParquetBreakdownItem[];
    by_resource?: ParquetBreakdownItem[];
    by_usage?: ParquetBreakdownItem[];
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
