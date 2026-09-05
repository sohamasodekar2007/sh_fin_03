"use client";

import { RefreshCw } from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { CostBreakdownPanelBody } from "@/components/finops/CostBreakdownPanelBody";
import { ForecastAnomalyPanelBody } from "@/components/finops/ForecastAnomalyPanelBody";
import { SpendVelocityPanelBody } from "@/components/finops/SpendVelocityPanelBody";
import { TeamAttributionPanelBody } from "@/components/finops/TeamAttributionPanelBody";
import { UnitEconomicsPanelBody } from "@/components/finops/UnitEconomicsPanelBody";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCostBreakdown,
  useForecastAnomaly,
  useSpendVelocityAlert,
  useSpendVelocitySeries,
  useTeamAttribution,
  useUnitEconomics,
} from "@/lib/queries";

function formatLastUpdated(updatedAt: number) {
  if (!updatedAt) return "Waiting";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(updatedAt));
}

function RealtimePanelAside({
  isFetching,
  updatedAt,
  onRefresh,
}: {
  isFetching: boolean;
  updatedAt: number;
  onRefresh: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-right text-[11px] leading-tight text-ink-faint sm:block">
        <span className="block font-medium text-foreground">{isFetching ? "Updating" : "Live 15s"}</span>
        <span className="num">Last {formatLastUpdated(updatedAt)}</span>
      </span>
      <Button size="sm" variant="outline" onClick={onRefresh} disabled={isFetching}>
        <RefreshCw className={isFetching ? "size-3.5 animate-spin" : "size-3.5"} />
        Refresh
      </Button>
    </div>
  );
}

/**
 * FinOps Intelligence — SpendShield-lite / DollarTrace-lite / MarginOS-lite.
 * All three are backed by cloudcare-fintech-addons/api, a standalone
 * FastAPI service (NEXT_PUBLIC_ADDON_API_URL, default localhost:8100), NOT
 * apps/api — same split as the Phase 14 panels on /dashboard/security-findings,
 * except this add-on lives entirely outside the main repo's backend. If that
 * service isn't running, every panel below degrades to a clear "couldn't
 * reach it" message, same discipline as the other .data?.error branches on
 * this page — never a crash.
 */
export default function FinOpsPage() {
  const alertQuery = useSpendVelocityAlert();
  const seriesQuery = useSpendVelocitySeries();
  const breakdownQuery = useCostBreakdown();
  const economicsQuery = useUnitEconomics();
  const forecastQuery = useForecastAnomaly();
  const teamQuery = useTeamAttribution();
  const spendUpdatedAt = Math.max(alertQuery.dataUpdatedAt, seriesQuery.dataUpdatedAt);
  const spendFetching = alertQuery.isFetching || seriesQuery.isFetching;

  return (
    <div className="mx-auto w-full max-w-[1400px]">
      <div className="stage py-1">
        <div className="eyebrow">FinOps intelligence</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">
          SpendShield · DollarTrace · MarginOS
        </h1>
        <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-ink-faint">
          Three category-defining features layered on the core 5-agent pipeline: a real-time spend-velocity circuit
          breaker (CUSUM-confirmed, not just a threshold), cost-delta attribution ranked by contribution, and
          gross-margin economics per merchant. Live below — see cloudcare-fintech-addons/README.md for the merge path.
        </p>
      </div>

      <div className="mt-4 grid gap-5 xl:grid-cols-2">
        <Panel
          eyebrow="SpendShield-lite · live"
          title="Spend Velocity Guard"
          subtitle="Windowed rate-ratio + CUSUM change-point confirmation. Estimated from usage metrics, never a billed figure — that lag is the whole point."
          aside={
            <RealtimePanelAside
              isFetching={spendFetching}
              updatedAt={spendUpdatedAt}
              onRefresh={() => {
                void alertQuery.refetch();
                void seriesQuery.refetch();
              }}
            />
          }
          delay={100}
        >
          {alertQuery.isLoading || seriesQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : alertQuery.isError ? (
            <p className="text-[12.5px] text-destructive">
              Could not reach the add-on API: {(alertQuery.error as { message?: string })?.message ?? "unknown error"}
            </p>
          ) : (
            <SpendVelocityPanelBody alert={alertQuery.data ?? null} series={seriesQuery.data ?? []} />
          )}
        </Panel>

        <Panel
          eyebrow="DollarTrace-lite"
          title="Cost Breakdown"
          subtitle="Ranks which dimension values explain a cost delta, by absolute contribution — co-occurrence attribution, not causal trace lineage."
          aside={
            <RealtimePanelAside
              isFetching={breakdownQuery.isFetching}
              updatedAt={breakdownQuery.dataUpdatedAt}
              onRefresh={() => {
                void breakdownQuery.refetch();
              }}
            />
          }
          delay={220}
        >
          {breakdownQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : breakdownQuery.isError ? (
            <p className="text-[12.5px] text-destructive">
              Could not reach the add-on API: {(breakdownQuery.error as { message?: string })?.message ?? "unknown error"}
            </p>
          ) : breakdownQuery.data ? (
            <CostBreakdownPanelBody breakdown={breakdownQuery.data} />
          ) : null}
        </Panel>
      </div>

      <div className="mt-5">
        <Panel
          eyebrow="MarginOS-lite"
          title="Unit Economics"
          subtitle="Cost-per-unit and gross margin per merchant. A scope with no revenue figure gets no margin claim at all, never a fabricated one."
          aside={
            <RealtimePanelAside
              isFetching={economicsQuery.isFetching}
              updatedAt={economicsQuery.dataUpdatedAt}
              onRefresh={() => {
                void economicsQuery.refetch();
              }}
            />
          }
          delay={340}
        >
          {economicsQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : economicsQuery.isError ? (
            <p className="text-[12.5px] text-destructive">
              Could not reach the add-on API: {(economicsQuery.error as { message?: string })?.message ?? "unknown error"}
            </p>
          ) : economicsQuery.data ? (
            <UnitEconomicsPanelBody summary={economicsQuery.data} />
          ) : null}
        </Panel>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel
          eyebrow="Forecast Anomaly Guard"
          title="Daily Cost Forecast"
          subtitle="Walk-forward: each day is forecast using only prior days, then compared to what actually happened — never a lookahead-biased fit."
          aside={
            <RealtimePanelAside
              isFetching={forecastQuery.isFetching}
              updatedAt={forecastQuery.dataUpdatedAt}
              onRefresh={() => {
                void forecastQuery.refetch();
              }}
            />
          }
          delay={100}
        >
          {forecastQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : forecastQuery.isError ? (
            <p className="text-[12.5px] text-destructive">
              Could not reach the add-on API: {(forecastQuery.error as { message?: string })?.message ?? "unknown error"}
            </p>
          ) : (
            <ForecastAnomalyPanelBody comparisons={forecastQuery.data ?? []} />
          )}
        </Panel>

        <Panel
          eyebrow="Tag-based attribution"
          title="Cost by Team"
          subtitle="Grouped by whatever tag key identifies a team at your org (case-insensitive) — untagged spend is its own line item, never hidden."
          aside={
            <RealtimePanelAside
              isFetching={teamQuery.isFetching}
              updatedAt={teamQuery.dataUpdatedAt}
              onRefresh={() => {
                void teamQuery.refetch();
              }}
            />
          }
          delay={220}
        >
          {teamQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : teamQuery.isError ? (
            <p className="text-[12.5px] text-destructive">
              Could not reach the add-on API: {(teamQuery.error as { message?: string })?.message ?? "unknown error"}
            </p>
          ) : teamQuery.data ? (
            <TeamAttributionPanelBody report={teamQuery.data} />
          ) : null}
        </Panel>
      </div>
    </div>
  );
}
