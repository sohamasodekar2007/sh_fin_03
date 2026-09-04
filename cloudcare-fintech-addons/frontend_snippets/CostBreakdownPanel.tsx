"use client";

import { useCallback, useEffect, useState } from "react";
import { PieChart, RefreshCw } from "lucide-react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const ADDON_API_URL = process.env.NEXT_PUBLIC_ADDON_API_URL ?? "http://localhost:8100";

type Contributor = {
  dimension_value: string;
  baseline_cost: number;
  current_cost: number;
  delta: number;
  pct_of_total_delta: number;
};

type CostBreakdown = {
  scope: string;
  dimension_key: string;
  total_delta: number;
  contributors: Contributor[];
  unattributed_pct: number;
  rationale: string;
};

function formatRupees(value: number): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}₹${Math.abs(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Contributor }[] }) {
  if (!active || !payload?.length) return null;
  const c = payload[0].payload;
  return (
    <div className="bg-surface border border-line rounded-lg px-3 py-2 text-[12px] shadow-card">
      <p className="font-mono text-ink mb-1">{c.dimension_value}</p>
      <p className="text-inkFaint">
        {formatRupees(c.baseline_cost)} → {formatRupees(c.current_cost)}
      </p>
      <p className={c.delta >= 0 ? "text-brandDanger" : "text-brandTeal"}>
        {formatRupees(c.delta)} ({c.pct_of_total_delta.toFixed(1)}%)
      </p>
    </div>
  );
}

export default function CostBreakdownPanel() {
  const [breakdown, setBreakdown] = useState<CostBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${ADDON_API_URL}/cost-attribution/demo-breakdown`)
      .then((res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setBreakdown(data);
        setError(null);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const chartData = breakdown
    ? [...breakdown.contributors].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    : [];

  return (
    <div className="bg-surface border border-line rounded-xl p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <PieChart size={16} className="text-inkFaint" />
          <p className="text-[12.5px] text-inkFaint">Cost Breakdown — why did this change?</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-inkFaint hover:text-ink transition-colors disabled:opacity-40"
          aria-label="Refresh cost breakdown"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {!breakdown && !error && <p className="text-[13px] text-inkFaint">Loading breakdown…</p>}
      {error && <p className="text-[13px] text-brandDanger">Add-on API unreachable ({error}).</p>}

      {breakdown && (
        <div>
          <p className="text-[13px] text-ink mb-3">
            Delta of <span className="font-mono">{formatRupees(breakdown.total_delta)}</span> on{" "}
            <span className="text-inkFaint">{breakdown.scope}</span>, by{" "}
            <span className="text-inkFaint">{breakdown.dimension_key}</span>
          </p>

          <div style={{ height: Math.max(120, chartData.length * 34) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="dimension_value"
                  width={72}
                  tick={{ fontSize: 11.5, fill: "#52697C", fontFamily: "IBM Plex Mono, monospace" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "#EAF2F6" }} />
                <Bar dataKey="delta" radius={[0, 4, 4, 0]}>
                  {chartData.map((c) => (
                    <Cell key={c.dimension_value} fill={c.delta >= 0 ? "#C0533E" : "#3FA796"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {breakdown.unattributed_pct !== 0 && (
            <p className="text-[12px] text-inkFaint mt-1">
              {breakdown.unattributed_pct.toFixed(1)}% unattributed to the contributors shown above.
            </p>
          )}
          <p className="text-[12px] text-inkFaint leading-relaxed border-t border-line pt-2 mt-3">{breakdown.rationale}</p>
        </div>
      )}
    </div>
  );
}
