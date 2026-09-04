"use client";

import { AgentActivityFeed } from "@/components/cfo/AgentActivityFeed";
import { Panel } from "@/components/cfo/Panel";
import { useAgentActivity } from "@/lib/queries";

export default function AgentActivityPage() {
  const agentActivityQuery = useAgentActivity(200);

  return (
    <div className="mx-auto w-full max-w-[1200px]">
      <div className="stage py-1">
        <div className="eyebrow">Live · polls every 30s</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">Agent activity</h1>
        <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-ink-faint">
          One row per Monitor / Analyzer / Decision / Supervisor / Executor run — real audit trail from the{" "}
          <code className="num text-[11px]">agent_runs</code> collection, not a mock feed. Click a row to expand its full JSON
          payload.
        </p>
      </div>

      <div className="mt-4">
        <Panel title="Recent runs" delay={140}>
          <AgentActivityFeed entries={agentActivityQuery.data ?? []} isLoading={agentActivityQuery.isLoading} />
        </Panel>
      </div>
    </div>
  );
}
