"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { addonApi } from "@/lib/finops-api";
import type {
  AgentActivityEntry,
  ConnectedAccount,
  CostSummary,
  ForecastPoint,
  IAMGovernanceOverview,
  ParquetAnalysis,
  Proposal,
  RDSRecommendationsResponse,
  ResourceItem,
  S3RecommendationsResponse,
  SecurityFindingsResponse,
} from "@/lib/cloudcare-data";
import type { CostBreakdown, SpendSeriesPoint, UnitEconomicsSummary, VelocityAlert } from "@/lib/finops-api";

/**
 * TanStack Query hooks for the dashboard. Operational surfaces poll on a
 * short interval so dashboard state follows the local backend/add-on APIs.
 */

export function useProposals() {
  return useQuery({
    queryKey: ["proposals"],
    // status="" (empty string) is falsy on the backend's `if status:`
    // check (apps/api/routers/supervisor.py's list_approvals) — the one
    // documented way to get every status back, not just pending.
    queryFn: () => api.get<Proposal[]>("/v1/approvals?status="),
    refetchInterval: 10_000,
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

export function useResources(filters?: { environment?: string; status?: string }) {
  const params = new URLSearchParams();
  if (filters?.environment) params.set("environment", filters.environment);
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return useQuery({
    queryKey: ["resources", filters?.environment ?? null, filters?.status ?? null],
    queryFn: () => api.get<ResourceItem[]>(`/v1/resources${qs ? `?${qs}` : ""}`),
    refetchInterval: 10_000,
  });
}

export function useCloudAccounts() {
  return useQuery({
    queryKey: ["cloud-accounts"],
    queryFn: () => api.get<ConnectedAccount[]>("/v1/cloud-accounts"),
    refetchInterval: 30_000,
  });
}

export function useIamGovernance() {
  return useQuery({
    queryKey: ["iam-governance"],
    queryFn: () => api.get<IAMGovernanceOverview>("/v1/governance/iam-overview"),
  });
}

export function useParquetAnalysis() {
  const params = new URLSearchParams();
  params.set("sample_limit", "50");
  return useQuery({
    queryKey: ["parquet-analysis", "s3-latest"],
    queryFn: () => api.get<ParquetAnalysis>(`/v1/parquet-analysis?${params.toString()}`),
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
