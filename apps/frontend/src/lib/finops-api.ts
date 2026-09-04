/**
 * Typed fetch client for the fintech add-ons standalone API
 * (cloudcare-fintech-addons/api) — NOT the main CloudCare backend. A
 * separate FastAPI service on NEXT_PUBLIC_ADDON_API_URL (default
 * http://localhost:8100). Deliberately its own tiny client rather than
 * routed through src/lib/api.ts: no auth token to attach (the add-on API
 * has none) and a different base URL entirely. See
 * cloudcare-fintech-addons/MERGE_GUIDE.md for folding this into the main
 * backend/client later — at that point this file and the finops hooks in
 * queries.ts can be deleted and repointed at `api`.
 */

const ADDON_API_BASE_URL = process.env.NEXT_PUBLIC_ADDON_API_URL || "http://localhost:8100";

export interface AddonApiError {
  status: number;
  message: string;
}

async function addonRequest<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${ADDON_API_BASE_URL}${path}`);
  } catch (err) {
    const apiError: AddonApiError = {
      status: 0,
      message: err instanceof Error ? err.message : "Network error — could not reach the fintech add-ons API.",
    };
    throw apiError;
  }
  if (!response.ok) {
    const apiError: AddonApiError = {
      status: response.status,
      message: response.statusText || `Request failed (${response.status})`,
    };
    throw apiError;
  }
  return (await response.json()) as T;
}

export const addonApi = {
  get: <T>(path: string) => addonRequest<T>(path),
};

// ---------------------------------------------------------------------------
// SpendShield-lite — spend-velocity circuit breaker
// (cloudcare-fintech-addons/spend_velocity/schemas.py)
// ---------------------------------------------------------------------------

export type FinopsSeverity = "low" | "medium" | "high" | "critical";

export interface VelocityReading {
  scope: string;
  window_end: string;
  baseline_hourly_rate: number;
  current_hourly_rate: number;
  velocity_ratio: number;
  sample_count: number;
  baseline_sample_count: number;
  confidence: number;
}

export interface VelocityAlert {
  alert_id: string;
  scope: string;
  severity: FinopsSeverity;
  reading: VelocityReading;
  recommended_action: string;
  rationale: string;
  requires_human_approval: boolean;
  projected_24h_cost: number;
  detected_at: string;
}

export interface SpendSeriesPoint {
  hours_ago: number;
  label: string;
  cost: number;
  phase: "baseline" | "current";
}

// ---------------------------------------------------------------------------
// DollarTrace-lite — cost-delta attribution
// (cloudcare-fintech-addons/cost_attribution/schemas.py)
// ---------------------------------------------------------------------------

export interface CostContributor {
  dimension_key: string;
  dimension_value: string;
  baseline_cost: number;
  current_cost: number;
  delta: number;
  pct_of_total_delta: number;
}

export interface CostBreakdown {
  scope: string;
  dimension_key: string;
  baseline_total: number;
  current_total: number;
  total_delta: number;
  contributors: CostContributor[];
  unattributed_delta: number;
  unattributed_pct: number;
  rationale: string;
}

// ---------------------------------------------------------------------------
// MarginOS-lite — unit economics
// (cloudcare-fintech-addons/unit_economics/schemas.py)
// ---------------------------------------------------------------------------

export interface MarginResult {
  scope: string;
  period: string;
  revenue: number;
  cost: number;
  gross_margin_pct: number;
  is_negative_margin: boolean;
  rationale: string;
}

export interface UnitEconomicsSummary {
  all_margins: MarginResult[];
  negative_margins: MarginResult[];
}
