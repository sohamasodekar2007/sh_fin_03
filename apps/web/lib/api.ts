// ---------------------------------------------------------------------------
// API HELPER — talks to the FastAPI backend
// ---------------------------------------------------------------------------
// Every function here fetches real data from the backend. If the backend is
// unreachable (not running, wrong URL, etc.) each function falls back to the
// mock data so your demo never shows a blank/broken screen.
// ---------------------------------------------------------------------------

import { getAuthHeaders } from "./auth";
import {
  kpis as mockKpis,
  resources as mockResources,
  agentActivity as mockAgentActivity,
  costTrend as mockCostTrend,
  type ResourceRow,
  type AgentActivityEntry,
} from "./mockData";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function safeFetch<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      cache: "no-store",
      headers: { ...(await getAuthHeaders()) },
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    return (await res.json()) as T;
  } catch (err) {
    console.warn(`[api] Falling back to mock data for ${path}:`, err);
    return fallback;
  }
}

// --- KPIs (from /v1/savings) ------------------------------------------------

export interface SavingsSummary {
  total_monthly_spend: number;
  wasted_spend_detected: number;
  wasted_spend_pct: number;
  savings_this_month: number;
  resources_monitored: number;
}

export async function fetchKpis() {
  const data = await safeFetch<SavingsSummary | null>("/v1/savings", null);
  if (!data) return mockKpis;

  return [
    { label: "Total monthly spend", value: `$${data.total_monthly_spend.toLocaleString()}`, tone: "neutral" as const },
    { label: "Wasted spend detected", value: `$${data.wasted_spend_detected.toLocaleString()}`, sub: `${data.wasted_spend_pct}%`, tone: "amber" as const },
    { label: "Savings this month", value: `$${data.savings_this_month.toLocaleString()}`, tone: "teal" as const },
    { label: "Resources monitored", value: `${data.resources_monitored}`, tone: "neutral" as const },
  ];
}

// --- Resources (from /v1/resources) -----------------------------------------

interface ApiResource {
  id: string;
  type: string;
  cpu_p95: number;
  status: ResourceRow["status"];
  monthly_cost_usd: number;
}

export async function fetchResources(): Promise<ResourceRow[]> {
  const data = await safeFetch<ApiResource[] | null>("/v1/resources", null);
  if (!data) return mockResources;

  return data.map((r) => ({
    id: r.id,
    type: r.type,
    cpu: Math.round(r.cpu_p95),
    status: r.status,
    monthlyCost: `$${r.monthly_cost_usd.toFixed(2)}`,
  }));
}

// --- Agent activity (from /v1/agent-activity) --------------------------------

export async function fetchAgentActivity(): Promise<AgentActivityEntry[]> {
  const data = await safeFetch<AgentActivityEntry[] | null>("/v1/agent-activity", null);
  return data ?? mockAgentActivity;
}

// --- Cost trend (from /v1/forecasts) -----------------------------------------

interface ApiForecastPoint {
  date: string;
  actual: number | null;
  predicted: number | null;
}

export async function fetchCostTrend() {
  const data = await safeFetch<ApiForecastPoint[] | null>("/v1/forecasts", null);
  if (!data) return mockCostTrend;

  return data.map((p) => ({
    day: p.date,
    cost: p.actual ?? p.predicted ?? 0,
  }));
}