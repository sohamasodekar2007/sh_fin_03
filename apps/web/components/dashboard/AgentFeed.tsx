"use client";

import { useEffect, useState } from "react";
import { fetchAgentActivity } from "@/lib/api";
import { agentActivity as mockAgentActivity, type AgentName } from "@/lib/mockData";

const agentColors: Record<AgentName, string> = {
  Monitor: "#2F6690",
  Analyzer: "#E2A93B",
  Decision: "#7f77dd",
  Supervisor: "#3FA796",
  Executor: "#D85A30",
};

export default function AgentFeed() {
  const [activity, setActivity] = useState(mockAgentActivity);

  useEffect(() => {
    fetchAgentActivity().then(setActivity);
  }, []);

  return (
    <div className="bg-surface border border-line rounded-xl p-5">
      <p className="text-[13px] font-semibold text-ink mb-4">Agent activity</p>
      <div className="flex flex-col gap-4">
        {activity.map((entry) => (
          <div key={entry.id} className="flex gap-3 items-start">
            <span
              className="mt-0.5 flex-none text-[10.5px] font-mono font-semibold px-2 py-0.5 rounded-full text-white"
              style={{ background: agentColors[entry.agent] }}
            >
              {entry.agent}
            </span>
            <div className="min-w-0">
              <p className="text-[13px] text-ink leading-snug">{entry.message}</p>
              <p className="text-[11px] text-inkFaint font-mono mt-0.5">{entry.timestamp}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}