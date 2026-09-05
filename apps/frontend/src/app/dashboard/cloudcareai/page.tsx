"use client";

import { Activity, Bot, CheckCircle2, Cloud, DollarSign, ShieldCheck, Sparkles } from "lucide-react";

import { ChatWindow } from "@/components/chat/ChatWindow";
import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { pendingApprovalsCount, projectedMonthlySavings } from "@/lib/cloudcare-data";
import { useAgentActivity, useCloudAccounts, useCostSummary, useProposals } from "@/lib/queries";

function compactCurrency(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function MetricTile({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Bot }) {
  return (
    <div className="rounded-md border border-hairline bg-surface-raised p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <Icon className="size-4 shrink-0 text-ink-faint" />
      </div>
      <div className="num mt-2 truncate text-[1.25rem] font-semibold leading-tight text-foreground">{value}</div>
    </div>
  );
}

export default function CloudCareAIPage() {
  const proposalsQuery = useProposals();
  const costSummaryQuery = useCostSummary(30);
  const activityQuery = useAgentActivity(8);
  const accountsQuery = useCloudAccounts();

  const proposals = proposalsQuery.data ?? [];
  const accounts = accountsQuery.data ?? [];
  const latestActivity = activityQuery.data ?? [];
  const connectedAccounts = accounts.filter((account) => account.connected && account.provider === "aws").length;
  const pendingApprovals = pendingApprovalsCount(proposals);
  const projectedSavings = projectedMonthlySavings(proposals);

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage flex flex-wrap items-end justify-between gap-4 py-1">
        <div>
          <div className="eyebrow">AWS-only FinOps copilot</div>
          <h1 className="mt-1 text-[clamp(1.5rem,2.8vw,2.25rem)] font-bold leading-[1.02] text-foreground">
            CloudCareAI
          </h1>
          <p className="mt-1.5 max-w-3xl text-[12.5px] leading-relaxed text-ink-faint">
            One AWS-only conversational control plane for spend, risk, approvals, agent runs, and workload design.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">
            <Sparkles className="mr-1 size-3.5" /> Tool-aware
          </Badge>
          <Badge variant="outline">
            <ShieldCheck className="mr-1 size-3.5" /> Human gated
          </Badge>
          <Badge variant="outline">
            <Cloud className="mr-1 size-3.5" /> AWS only
          </Badge>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {proposalsQuery.isLoading || costSummaryQuery.isLoading ? (
          <>
            <Skeleton className="h-[86px] w-full" />
            <Skeleton className="h-[86px] w-full" />
            <Skeleton className="h-[86px] w-full" />
            <Skeleton className="h-[86px] w-full" />
          </>
        ) : (
          <>
            <MetricTile label="30d spend" value={compactCurrency(costSummaryQuery.data?.total_cost_usd)} icon={DollarSign} />
            <MetricTile label="Projected savings" value={compactCurrency(projectedSavings)} icon={CheckCircle2} />
            <MetricTile label="Pending approvals" value={pendingApprovals.toLocaleString()} icon={ShieldCheck} />
            <MetricTile label="Connected AWS accounts" value={connectedAccounts.toLocaleString()} icon={Cloud} />
          </>
        )}
      </div>

      <div className="mt-4 grid min-h-[680px] gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <ChatWindow />

        <div className="space-y-4">
          <Panel title="Live agent trail" bodyClassName="px-5 pb-5 sm:px-6 sm:pb-6">
            {activityQuery.isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : latestActivity.length === 0 ? (
              <div className="rounded-md border border-hairline bg-surface-raised p-4 text-[12.5px] text-ink-faint">
                No agent runs recorded yet.
              </div>
            ) : (
              <div className="space-y-3">
                {latestActivity.map((entry) => (
                  <div key={entry.id} className="rounded-md border border-hairline bg-surface-raised p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <Activity className="size-4 shrink-0 text-signal" />
                        <span className="truncate text-[12.5px] font-medium text-foreground">{entry.agent}</span>
                      </div>
                      <Badge variant={entry.status === "success" ? "secondary" : "outline"} className="text-[10px]">
                        {entry.status}
                      </Badge>
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-[11.5px] leading-relaxed text-ink-faint">{entry.message}</p>
                    <div className="num mt-2 text-[10.5px] text-ink-faint">{new Date(entry.timestamp).toLocaleString()}</div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Decision posture" bodyClassName="px-5 pb-5 sm:px-6 sm:pb-6">
            <div className="space-y-3 text-[12.5px]">
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink-faint">AWS action authority</span>
                <Badge variant="outline">Human approval</Badge>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink-faint">Execution path</span>
                <Badge variant="secondary">Guarded</Badge>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink-faint">Evidence standard</span>
                <Badge variant="outline">Tool data</Badge>
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
