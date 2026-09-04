"use client";

import { useCallback, useEffect, useState } from "react";
import { IndianRupee, RefreshCw } from "lucide-react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const ADDON_API_URL = process.env.NEXT_PUBLIC_ADDON_API_URL ?? "http://localhost:8100";

type MarginResult = {
  scope: string;
  period: string;
  revenue: number;
  cost: number;
  gross_margin_pct: number;
  is_negative_margin: boolean;
  rationale: string;
};

type DemoSummary = {
  all_margins: MarginResult[];
  negative_margins: MarginResult[];
};

function formatRupees(value: number): string {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function marginColor(pct: number): string {
  if (pct < 0) return "#C0533E";
  if (pct < 40) return "#E2A93B";
  return "#3FA796";
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: MarginResult }[] }) {
  if (!active || !payload?.length) return null;
  const m = payload[0].payload;
  return (
    <div className="bg-surface border border-line rounded-lg px-3 py-2 text-[12px] shadow-card">
      <p className="font-mono text-ink mb-1">{m.scope}</p>
      <p className="text-inkFaint">
        {formatRupees(m.revenue)} rev · {formatRupees(m.cost)} cost
      </p>
      <p style={{ color: marginColor(m.gross_margin_pct) }}>{m.gross_margin_pct.toFixed(1)}% margin</p>
    </div>
  );
}

export default function UnitEconomicsCard() {
  const [summary, setSummary] = useState<DemoSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${ADDON_API_URL}/unit-economics/demo-summary`)
      .then((res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setSummary(data);
        setError(null);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="bg-surface border border-line rounded-xl p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <IndianRupee size={16} className="text-inkFaint" />
          <p className="text-[12.5px] text-inkFaint">Unit Economics — margin by merchant</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-inkFaint hover:text-ink transition-colors disabled:opacity-40"
          aria-label="Refresh unit economics"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {!summary && !error && <p className="text-[13px] text-inkFaint">Loading unit economics…</p>}
      {error && <p className="text-[13px] text-brandDanger">Add-on API unreachable ({error}).</p>}

      {summary && (
        <div>
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.all_margins} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <XAxis
                  dataKey="scope"
                  tick={{ fontSize: 10.5, fill: "#8CA0AE" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v: string) => v.replace("merchant-", "")}
                />
                <YAxis tick={{ fontSize: 10.5, fill: "#8CA0AE" }} axisLine={false} tickLine={false} width={36} />
                <ReferenceLine y={0} stroke="#DCE7EC" />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "#EAF2F6" }} />
                <Bar dataKey="gross_margin_pct" radius={[4, 4, 0, 0]}>
                  {summary.all_margins.map((m) => (
                    <Cell key={m.scope} fill={marginColor(m.gross_margin_pct)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {summary.negative_margins.length > 0 && (
            <div className="mt-2 pt-3 border-t border-line">
              <p className="text-[11.5px] uppercase tracking-wide text-brandDanger mb-1.5">
                {summary.negative_margins.length} scope(s) below margin floor
              </p>
              {summary.negative_margins.map((m) => (
                <p key={m.scope} className="text-[12px] text-inkFaint leading-relaxed mb-1">
                  {m.rationale}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
