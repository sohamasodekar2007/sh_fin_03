"use client";

import { useEffect, useState } from "react";
import { fetchKpis } from "@/lib/api";
import { kpis as mockKpis } from "@/lib/mockData";


const toneStyles: Record<string, string> = {
  neutral: "text-ink",
  amber: "text-[#B8842E]",
  teal: "text-[#0F6E56]",
};


export default function KpiCards() {
  const [kpis, setKpis] = useState(mockKpis);

  useEffect(() => {
    fetchKpis().then(setKpis);
  }, []);
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {kpis.map((kpi) => (
        <div key={kpi.label} className="bg-surface border border-line rounded-xl p-5">
          <p className="text-[12.5px] text-inkFaint mb-2">{kpi.label}</p>
          <div className="flex items-baseline gap-2">
            <span className={`font-display text-2xl font-semibold ${toneStyles[kpi.tone]}`}>{kpi.value}</span>
            {"sub" in kpi && kpi.sub && <span className="text-[12.5px] font-mono text-inkFaint">{kpi.sub}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
