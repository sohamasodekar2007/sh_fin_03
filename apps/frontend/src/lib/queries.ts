"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { awsFocusSampleAnalysis } from "@/lib/aws-focus-sample";
import { addonApi } from "@/lib/finops-api";
import type {
  AgentActivityEntry,
  ChatMcpSetupResponse,
  ConnectedAccount,
  CostSummary,
  ForecastPoint,
  IAMGovernanceOverview,
  ParquetAnalysis,
  Proposal,
  RDSRecommendationsResponse,
  ResourceDetail,
  ResourceItem,
  S3RecommendationsResponse,
  SecurityFindingsResponse,
} from "@/lib/cloudcare-data";
import type {
  CostBreakdown,
  ForecastComparison,
  SecurityPolicyFinding,
  SpendSeriesPoint,
  TeamAttributionReport,
  TrustedServicesReport,
  TrustScorecard,
  UnitEconomicsSummary,
  VelocityAlert,
} from "@/lib/finops-api";

/**
 * TanStack Query hooks for the dashboard. Operational surfaces poll on a
 * short interval so dashboard state follows the local backend/add-on APIs.
 */

export function useProposals(options: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: ["proposals"],
    // status="" (empty string) is falsy on the backend's `if status:`
    // check (apps/api/routers/supervisor.py's list_approvals) — the one
    // documented way to get every status back, not just pending.
    queryFn: () => api.get<Proposal[]>("/v1/approvals?status="),
    refetchInterval: options.refetchInterval ?? 10_000,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export function useCostSummary(periodDays: number) {
  return useQuery({
    queryKey: ["cost-summary", periodDays],
    queryFn: () => api.get<CostSummary>(`/v1/focus/cost-summary?period_days=${periodDays}`),
    refetchInterval: 30_000,
  });
}

export function useForecasts() {
  return useQuery({
    queryKey: ["forecasts"],
    queryFn: () => api.get<ForecastPoint[]>("/v1/forecasts"),
    refetchInterval: 30_000,
  });
}

export function useAgentActivity(limit = 50) {
  return useQuery({
    queryKey: ["agent-activity", limit],
    queryFn: () => api.get<AgentActivityEntry[]>(`/v1/agent-activity?limit=${limit}`),
    refetchInterval: 30_000,
  });
}

export function useResources(
  filters?: { environment?: string; status?: string },
  options: { refetchInterval?: number | false } = {},
) {
  const params = new URLSearchParams();
  if (filters?.environment) params.set("environment", filters.environment);
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return useQuery({
    queryKey: ["resources", filters?.environment ?? null, filters?.status ?? null],
    queryFn: () => api.get<ResourceItem[]>(`/v1/resources${qs ? `?${qs}` : ""}`),
    refetchInterval: options.refetchInterval ?? 10_000,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export function useResourceDetail(resourceId: string | null, resourceType?: string | null) {
  const params = new URLSearchParams();
  if (resourceType) params.set("resource_type", resourceType);
  const qs = params.toString();
  return useQuery({
    queryKey: ["resource-detail", resourceId, resourceType ?? null],
    queryFn: () => api.get<ResourceDetail>(`/v1/resources/${encodeURIComponent(resourceId as string)}${qs ? `?${qs}` : ""}`),
    enabled: resourceId != null,
    // 30s while the detail sheet is open — the same 15-min collector cycle
    // backs it, but a shorter poll here means a resource that just got a
    // new proposal or execution shows up without the viewer closing and
    // reopening the sheet.
    refetchInterval: 30_000,
  });
}

export function useCloudAccounts() {
  return useQuery({
    queryKey: ["cloud-accounts"],
    queryFn: () => api.get<ConnectedAccount[]>("/v1/cloud-accounts"),
    refetchInterval: 30_000,
  });
}

export function useChatMcpSetup() {
  return useQuery({
    queryKey: ["chat-mcp-setup"],
    queryFn: () => api.get<ChatMcpSetupResponse>("/v1/chat/mcp/setup"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true,
  });
}

export function useIamGovernance(options: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: ["iam-governance"],
    queryFn: () => api.get<IAMGovernanceOverview>("/v1/governance/iam-overview"),
    refetchInterval: options.refetchInterval ?? 30_000,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

export function useParquetAnalysis(options: { source?: "s3" | "local" } = {}) {
  const params = new URLSearchParams();
  params.set("sample_limit", "50");
  if (options.source) params.set("source", options.source);
  return useQuery({
    queryKey: ["parquet-analysis", options.source ?? "s3-latest"],
    queryFn: async () => {
      try {
        return await api.get<ParquetAnalysis>(`/v1/parquet-analysis?${params.toString()}`);
      } catch (error) {
        if (options.source === "local") return awsFocusSampleAnalysis();
        throw error;
      }
    },
    refetchInterval: 60_000,
  });
}

// Phase 14 — services/phase14/, apps/api/routers/phase14.py. Additive
// only; removing that package/router is the only thing that would make
// these hooks start failing, and the failure would be a clean 404, not a
// crash anywhere else in the app.

export function useRdsRecommendations() {
  return useQuery({
    queryKey: ["phase14-rds-recommendations"],
    queryFn: () => api.get<RDSRecommendationsResponse>("/v1/phase14/rds-recommendations"),
  });
}

export function useS3Recommendations() {
  return useQuery({
    queryKey: ["phase14-s3-recommendations"],
    queryFn: () => api.get<S3RecommendationsResponse>("/v1/phase14/s3-recommendations"),
  });
}

export function useSecurityFindings() {
  return useQuery({
    queryKey: ["phase14-security-findings"],
    queryFn: () => api.get<SecurityFindingsResponse>("/v1/phase14/security-findings"),
  });
}

// ---------------------------------------------------------------------------
// Fintech add-ons (SpendShield-lite / DollarTrace-lite / MarginOS-lite) —
// cloudcare-fintech-addons/api, a standalone FastAPI service, NOT the main
// backend (see src/lib/finops-api.ts). Same "additive only" discipline as
// the Phase 14 hooks above: deleting cloudcare-fintech-addons/ is the only
// thing that makes these start failing, and it fails as a clean
// unreachable-API state on each card, not a crash anywhere else in the app.
// `retry: false` — an add-on that isn't running should read as "not
// running" within one request, not after react-query's default 3 retries.
// ---------------------------------------------------------------------------

export function useSpendVelocityAlert() {
  return useQuery({
    queryKey: ["finops-spend-velocity-alert"],
    queryFn: () => addonApi.get<VelocityAlert | null>("/spend-velocity/demo-alert?live=true"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true,
    retry: false,
  });
}

export function useSpendVelocitySeries() {
  return useQuery({
    queryKey: ["finops-spend-velocity-series"],
    queryFn: () => addonApi.get<SpendSeriesPoint[]>("/spend-velocity/demo-series?live=true&hours_back=16"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true,
    retry: false,
  });
}

export function useCostBreakdown() {
  return useQuery({
    queryKey: ["finops-cost-breakdown"],
    queryFn: () => addonApi.get<CostBreakdown>("/cost-attribution/demo-breakdown"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true,
    retry: false,
  });
}

export function useUnitEconomics() {
  return useQuery({
    queryKey: ["finops-unit-economics"],
    queryFn: () => addonApi.get<UnitEconomicsSummary>("/unit-economics/demo-summary"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true,
    retry: false,
  });
}

export function useForecastAnomaly() {
  return useQuery({
    queryKey: ["finops-forecast-anomaly"],
    queryFn: () => addonApi.get<ForecastComparison[]>("/forecast-anomaly/demo-series"),
    retry: false,
  });
}

export function useTeamAttribution(tagKey = "team") {
  return useQuery({
    queryKey: ["finops-team-attribution", tagKey],
    queryFn: () => addonApi.get<TeamAttributionReport>(`/team-attribution/demo-report?tag_key=${encodeURIComponent(tagKey)}`),
    retry: false,
  });
}

export function useSecurityPolicyAddons() {
  return useQuery({
    queryKey: ["finops-security-policy-addons"],
    queryFn: () => addonApi.get<{ findings: SecurityPolicyFinding[] }>("/security-policy-addons/demo-findings"),
    retry: false,
  });
}

export function useTrustedServicesAllowlist() {
  return useQuery({
    queryKey: ["finops-trusted-services-allowlist"],
    queryFn: () => addonApi.get<TrustedServicesReport>("/aws-trusted-services/demo-allowlist-report"),
    retry: false,
  });
}

export function useTrustScorecard() {
  return useQuery({
    queryKey: ["finops-trust-scorecard"],
    queryFn: () => addonApi.get<TrustScorecard>("/aws-trusted-services/demo-scorecard"),
    retry: false,
  });
}
