"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ShieldAlert, TrendingUp } from "lucide-react";
import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from "recharts";

const ADDON_API_URL = process.env.NEXT_PUBLIC_ADDON_API_URL ?? "http://localhost:8100";
const POLL_INTERVAL_MS = 15_000;

type Severity = "low" | "medium" | "high" | "critical";

type VelocityAlert = {
  alert_id: string;
  scope: string;
  severity: Severity;
  reading: {
    baseline_hourly_rate: number;
    current_hourly_rate: number;
    velocity_ratio: number;
    confidence: number;
  };
  recommended_action: string;
  rationale: string;
  requires_human_approval: boolean;
  projected_24h_cost: number;
};

type SeriesPoint = { label: string; cost: number; phase: "baseline" | "current" };

const severityColor: Record<Severity, string> = {
  low: "#3FA796",
  medium: "#E2A93B",
  high: "#E2A93B",
  critical: "#C0533E",
};

const severityText: Record<Severity, string> = {
  low: "text-brandTeal",
  medium: "text-brandAmber",
  high: "text-brandAmber",
  critical: "text-brandDanger",
};

function formatRupees(value: number): string {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function useRelativeTime(timestamp: number | null): string {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  if (!timestamp) return "—";
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 2) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.floor(seconds / 60)}m ago`;
}

export default function SpendVelocityCard() {
  const [alert, setAlert] = useState<VelocityAlert | null | undefined>(undefined);
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const [alertRes, seriesRes] = await Promise.all([
        fetch(`${ADDON_API_URL}/spend-velocity/demo-alert?live=true`),
        fetch(`${ADDON_API_URL}/spend-velocity/demo-series?live=true&hours_back=16`),
      ]);
      if (!alertRes.ok) throw new Error(`alert status ${alertRes.status}`);
      if (!seriesRes.ok) throw new Error(`series status ${seriesRes.status}`);
      setAlert(await alertRes.json());
      setSeries(await seriesRes.json());
      setLastUpdated(Date.now());
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const relativeTime = useRelativeTime(lastUpdated);
  const color = alert ? severityColor[alert.severity] : "#3FA796";
  const baselineAvg =
    series.filter((p) => p.phase === "baseline").reduce((sum, p, _i, arr) => sum + p.cost / arr.length, 0) || 0;

  return (
    <div className="bg-surface border border-line rounded-xl p-5 shadow-card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} className="text-inkFaint" />
          <p className="text-[12.5px] text-inkFaint">Spend Velocity Guard</p>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brandTeal opacity-60" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-brandTeal" />
          </span>
          <span className="text-[11px] text-inkFaint font-mono">live · {relativeTime}</span>
        </div>
      </div>

      {alert === undefined && !error && <p className="text-[13px] text-inkFaint">Checking spend velocity…</p>}
      {error && (
        <p className="text-[13px] text-brandDanger">
          Add-on API unreachable ({error}). Is it running on {ADDON_API_URL}?
        </p>
      )}

      {alert === null && (
        <div className="flex items-center gap-2">
          <TrendingUp size={16} className="text-brandTeal" />
          <p className="text-[13px] text-ink">No velocity anomalies detected.</p>
        </div>
      )}

      {alert && (
        <div>
          <div className="flex items-baseline gap-2 mb-1">
            <AlertTriangle size={16} className={severityText[alert.severity]} />
            <span className={`font-display text-xl font-semibold ${severityText[alert.severity]}`}>
              {alert.severity.toUpperCase()}
            </span>
            <span className="text-[12.5px] font-mono text-inkFaint">{alert.scope}</span>
          </div>

          <div className="flex items-baseline gap-4 mb-2">
            <div>
              <p className="text-[11px] text-inkFaint">current</p>
              <p className="font-mono text-[15px] text-ink">{formatRupees(alert.reading.current_hourly_rate)}/hr</p>
            </div>
            <div>
              <p className="text-[11px] text-inkFaint">baseline</p>
              <p className="font-mono text-[15px] text-inkSoft">{formatRupees(alert.reading.baseline_hourly_rate)}/hr</p>
            </div>
            <div>
              <p className="text-[11px] text-inkFaint">ratio</p>
              <p className="font-mono text-[15px]" style={{ color }}>
                {alert.reading.velocity_ratio >= 1000 ? "new" : `${alert.reading.velocity_ratio.toFixed(1)}x`}
              </p>
            </div>
          </div>

          {series.length > 0 && (
            <div className="h-16 -mx-1 mb-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                  <defs>
                    <linearGradient id="svg-cost-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="label" hide />
                  {baselineAvg > 0 && (
                    <ReferenceLine y={baselineAvg} stroke="#8CA0AE" strokeDasharray="3 3" strokeWidth={1} />
                  )}
                  <Tooltip
                    formatter={(value: number) => [formatRupees(value), "cost"]}
                    labelFormatter={(label) => `${label}`}
                    contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#DCE7EC" }}
                  />
                  <Area type="monotone" dataKey="cost" stroke={color} strokeWidth={2} fill="url(#svg-cost-fill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          <p className="text-[12.5px] text-inkFaint mb-3">
            Projected 24h impact: <span className="font-mono text-ink">{formatRupees(alert.projected_24h_cost)}</span>
          </p>

          <div className="text-[12px] text-inkFaint leading-relaxed border-t border-line pt-2">{alert.rationale}</div>

          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <span className="text-[11.5px] uppercase tracking-wide text-inkFaint">Recommended:</span>
            <span className="text-[12.5px] font-mono text-ink">{alert.recommended_action.replace(/_/g, " ")}</span>
            {alert.requires_human_approval && (
              <span className="text-[11px] px-2 py-0.5 rounded-full border border-line text-inkFaint">needs approval</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
