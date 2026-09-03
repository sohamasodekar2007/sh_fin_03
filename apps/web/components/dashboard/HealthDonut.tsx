"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { healthBreakdown } from "@/lib/mockData";

export default function HealthDonut() {
  return (
    <div className="bg-surface border border-line rounded-xl p-5">
      <p className="text-[13px] font-semibold text-ink mb-1">Resource health breakdown</p>
      <p className="text-[12px] text-inkFaint mb-2">Across all 47 monitored resources.</p>
      <div className="h-56 flex items-center">
        <ResponsiveContainer width="55%" height="100%">
          <PieChart>
            <Pie data={healthBreakdown} dataKey="value" nameKey="name" innerRadius={45} outerRadius={70} paddingAngle={2}>
              {healthBreakdown.map((entry) => (
                <Cell key={entry.name} fill={entry.color} stroke="none" />
              ))}
            </Pie>
            <Tooltip formatter={(value: number, name: string) => [`${value}%`, name]} contentStyle={{ borderRadius: 10, borderColor: "#DCE7EC", fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
        <div className="flex flex-col gap-2">
          {healthBreakdown.map((h) => (
            <div key={h.name} className="flex items-center gap-2 text-[12.5px] text-inkSoft">
              <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: h.color }} />
              {h.name} · {h.value}%
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
