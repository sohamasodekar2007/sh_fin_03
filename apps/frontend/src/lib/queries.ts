"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { AgentActivityEntry, CostSummary, ForecastPoint, Proposal } from "@/lib/cloudcare-data";

/**
 * TanStack Query hooks for the dashboard. Agent activity polls every 30s
 * (item: "poll agent-activity every 30s; everything else on demand") —
 * everything else only refetches on mount / explicit invalidation /
 * control-bar changes (via query key).
 */

export function useProposals() {
  return useQuery({
    queryKey: ["proposals"],
    // status="" (empty string) is falsy on the backend's `if status:`
    // check (apps/api/routers/supervisor.py's list_approvals) — the one
    // documented way to get every status back, not just pending.
    queryFn: () => api.get<Proposal[]>("/v1/approvals?status="),
  });
}

export function useCostSummary(periodDays: number) {
  return useQuery({
    queryKey: ["cost-summary", periodDays],
    queryFn: () => api.get<CostSummary>(`/v1/focus/cost-summary?period_days=${periodDays}`),
  });
}

export function useForecasts() {
  return useQuery({
    queryKey: ["forecasts"],
    queryFn: () => api.get<ForecastPoint[]>("/v1/forecasts"),
  });
}

export function useAgentActivity() {
  return useQuery({
    queryKey: ["agent-activity"],
    queryFn: () => api.get<AgentActivityEntry[]>("/v1/agent-activity?limit=50"),
    refetchInterval: 30_000,
  });
}
