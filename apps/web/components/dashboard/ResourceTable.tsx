"use client";

import { useEffect, useState } from "react";
import { fetchResources } from "@/lib/api";
import { resources as mockResources, type ResourceStatus } from "@/lib/mockData";

const statusStyles: Record<ResourceStatus, string> = {
  Healthy: "bg-[#EAF3DE] text-[#3B6D11]",
  Idle: "bg-[#FAEEDA] text-[#854F0B]",
  "Over-provisioned": "bg-[#E6F1FB] text-[#0C447C]",
  "At-risk": "bg-[#FCEBEB] text-[#791F1F]",
};

export default function ResourceTable() {
  const [resources, setResources] = useState(mockResources);

  useEffect(() => {
    fetchResources().then(setResources);
  }, []);

  return (
    <div className="bg-surface border border-line rounded-xl p-5 overflow-x-auto">
      <p className="text-[13px] font-semibold text-ink mb-4">Resources</p>
      <table className="w-full text-left border-collapse min-w-[560px]">
        <thead>
          <tr className="text-[11.5px] text-inkFaint uppercase tracking-wide">
            <th className="pb-2 font-medium">Instance ID</th>
            <th className="pb-2 font-medium">Type</th>
            <th className="pb-2 font-medium">CPU</th>
            <th className="pb-2 font-medium">Status</th>
            <th className="pb-2 font-medium text-right">Monthly cost</th>
          </tr>
        </thead>
        <tbody>
          {resources.map((r) => (
            <tr key={r.id} className="border-t border-line">
              <td className="py-2.5 font-mono text-[12.5px] text-ink">{r.id}</td>
              <td className="py-2.5 text-[13px] text-inkSoft">{r.type}</td>
              <td className="py-2.5 text-[13px] text-inkSoft w-28">
                <div className="flex items-center gap-2">
                  <div className="w-14 h-1.5 rounded-full bg-surfaceAlt overflow-hidden">
                    <div className="h-full rounded-full bg-brandBlue" style={{ width: `${Math.min(r.cpu, 100)}%` }} />
                  </div>
                  <span>{r.cpu}%</span>
                </div>
              </td>
              <td className="py-2.5">
                <span className={`text-[11.5px] font-medium px-2.5 py-1 rounded-full ${statusStyles[r.status]}`}>
                  {r.status}
                </span>
              </td>
              <td className="py-2.5 text-[13px] text-ink text-right font-medium">{r.monthlyCost}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}