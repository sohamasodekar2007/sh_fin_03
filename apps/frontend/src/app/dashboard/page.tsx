"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

import { CashFanChart } from "@/components/cfo/CashFanChart";
import { ControlBar } from "@/components/cfo/ControlBar";
import { KpiStrip, type Kpi } from "@/components/cfo/KpiStrip";
import { Panel } from "@/components/cfo/Panel";
import { SankeyFlow } from "@/components/cfo/SankeyFlow";
import { VariancePanel } from "@/components/cfo/VariancePanel";
import { VarianceWaterfall } from "@/components/cfo/VarianceWaterfall";
import { Skeleton } from "@/components/ui/skeleton";
import {
  buildCostWaterfall,
  costDeltaPct,
  costFlowFromProposals,
  deriveProvider,
  pendingApprovalsCount,
  projectedMonthlySavings,
  type Provider,
} from "@/lib/cloudcare-data";
import { useStage } from "@/lib/motion";
import { useCostSummary, useForecasts, useProposals } from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";

/**
 * Overview — the executive summary. Full proposal table lives at
 * /dashboard/proposals now; this page keeps only what a first glance
 * needs: spend/savings KPIs, the cost-flow hero, the forecast, and the
 * current->optimized waterfall (still "THE key panel").
 */

function PanelSkeleton({ height }: { height: number }) {
  return <Skeleton className="w-full" style={{ height }} />;
}

export default function DashboardOverviewPage() {
  const queryClient = useQueryClient();

  const [providerFilter, setProviderFilter] = useState<Provider | "all">("all");
  const [periodDays, setPeriodDays] = useState(30);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);

  const proposalsQuery = useProposals();
  const costSummaryQuery = useCostSummary(periodDays);
  const forecastsQuery = useForecasts();

  const allProposals = useMemo(() => proposalsQuery.data ?? [], [proposalsQuery.data]);
  const providers = useMemo(() => Array.from(new Set(allProposals.map((p) => deriveProvider(p.resource_arn)))), [allProposals]);
  const proposals = useMemo(
    () => (providerFilter === "all" ? allProposals : allProposals.filter((p) => deriveProvider(p.resource_arn) === providerFilter)),
    [allProposals, providerFilter],
  );

  const heroOn = useStage(260);
  const forecastOn = useStage(480);
  const waterfallOn = useStage(700);

  const kpis: Kpi[] = [
    {
      label: "Current monthly spend",
      value: costSummaryQuery.data?.total_cost_usd ?? null,
      fmt: "usdCompact",
      delta: costDeltaPct(costSummaryQuery.data),
      deltaLabel: `vs prior ${periodDays}d`,
      hint: `Sum of FOCUS BilledCost across every connected account's most recent ingest, trailing ${periodDays} days.`,
    },
    {
      label: "Projected monthly savings",
      value: proposalsQuery.data ? projectedMonthlySavings(proposals) : null,
      fmt: "usdCompact",
      delta: null,
      deltaLabel: "approved + pending",
      tone: "mint",
      hint: "Sum of expected_monthly_savings across proposals that are approved or awaiting approval.",
    },
    {
      label: "Resources monitored",
      value: costSummaryQuery.data?.resource_count ?? null,
      fmt: "count",
      delta: null,
      deltaLabel: "distinct ResourceId",
      hint: "Distinct FOCUS ResourceId across the tenant's latest ingested datasets.",
    },
    {
      label: "Pending approvals",
      value: proposalsQuery.data ? pendingApprovalsCount(proposals) : null,
      fmt: "count",
      delta: null,
      deltaLabel: "awaiting a decision",
      tone: "signal",
      hint: "Proposals the Supervisor scored and is waiting on a human approve/reject for.",
    },
  ];

  const waterfallSteps = useMemo(() => buildCostWaterfall(proposals), [proposals]);
  const costFlowRecords = useMemo(() => costFlowFromProposals(proposals), [proposals]);
  const selectedProposal = useMemo(() => allProposals.find((p) => p.proposal_id === selectedProposalId) ?? null, [allProposals, selectedProposalId]);

  function handleDecided() {
    queryClient.invalidateQueries({ queryKey: ["proposals"] });
  }

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage py-1">
        <h1 className="text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">Cost command center</h1>
      </div>

      <div className="mt-3">
        <ControlBar providers={providers} provider={providerFilter} onProvider={setProviderFilter} periodDays={periodDays} onPeriodDays={setPeriodDays} />
      </div>

      <div className="mt-4">
        {proposalsQuery.isLoading && costSummaryQuery.isLoading ? (
          <div className="panel hairline-top grid grid-cols-2 gap-px sm:grid-cols-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : (
          <KpiStrip kpis={kpis} />
        )}
      </div>

      <div className="mt-4">
        <Panel
          eyebrow="Hero · cost flow"
          title="Where every dollar is going"
          subtitle="Provider → service category → service → environment. Hover or use arrow keys to trace any ribbon."
          delay={260}
          headerClassName="px-5 pb-3 pt-4 sm:px-6 sm:pb-3 sm:pt-5"
          bodyClassName="px-2 pb-4 sm:px-4 sm:pb-6"
          empty={
            proposalsQuery.isLoading ? undefined : costFlowRecords.length === 0 ? (
              <>
                No costed proposals yet — connect an account and run the Monitor agent from{" "}
                <Link className="underline" href="/onboarding">
                  onboarding
                </Link>
                .
              </>
            ) : undefined
          }
        >
          {proposalsQuery.isLoading ? <PanelSkeleton height={460} /> : <SankeyFlow records={costFlowRecords} stateKey={`${providerFilter}|${proposals.length}`} active={heroOn} height={460} />}
        </Panel>
      </div>

      <div className="mt-5">
        <Panel eyebrow="Trend" title="Daily cost forecast" subtitle="Solid: actual. Dashed: model prediction (services/forecasting)." delay={420}>
          {forecastsQuery.isLoading ? <PanelSkeleton height={240} /> : <CashFanChart points={forecastsQuery.data ?? []} active={forecastOn} height={240} />}
        </Panel>
      </div>

      <div className="mt-5">
        <Panel
          eyebrow="Current → optimized"
          title="Cost transition"
          subtitle="Current monthly cost, one step per proposal, optimized monthly cost. Click a step for evidence."
          delay={620}
        >
          {proposalsQuery.isLoading ? (
            <PanelSkeleton height={236} />
          ) : (
            <VarianceWaterfall steps={waterfallSteps} active={waterfallOn} selected={selectedProposalId} onSelect={setSelectedProposalId} />
          )}
        </Panel>
      </div>

      <footer className="stage mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-5">
        <p className="num text-[10.5px] tracking-[0.04em] text-ink-faint">CloudCare · multi-cloud FinOps</p>
        <p className="num text-[10.5px] tracking-[0.04em] text-ink-faint">{allProposals.length} proposals tracked</p>
      </footer>

      <VariancePanel proposal={selectedProposal} onClose={() => setSelectedProposalId(null)} onDecided={handleDecided} />
    </div>
  );
}
