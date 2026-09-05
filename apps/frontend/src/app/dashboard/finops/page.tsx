"use client";

import { RefreshCw } from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { AwsFocusCostPanelBody } from "@/components/finops/AwsFocusCostPanelBody";
import { AwsFocusUnitSignalsPanelBody } from "@/components/finops/AwsFocusUnitSignalsPanelBody";
import { ForecastAnomalyPanelBody } from "@/components/finops/ForecastAnomalyPanelBody";
import { SpendVelocityPanelBody } from "@/components/finops/SpendVelocityPanelBody";
import { TeamAttributionPanelBody } from "@/components/finops/TeamAttributionPanelBody";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api";
import {
  useForecastAnomaly,
  useParquetAnalysis,
  useSpendVelocityAlert,
  useSpendVelocitySeries,
  useTeamAttribution,
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
  statusLabel = "Live 15s",
}: {
  isFetching: boolean;
  updatedAt: number;
  onRefresh: () => void;
  statusLabel?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-right text-[11px] leading-tight text-ink-faint sm:block">
        <span className="block font-medium text-foreground">{isFetching ? "Updating" : statusLabel}</span>
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
 * FinOps Intelligence combines the real-time add-on monitors with the AWS
 * FOCUS Parquet export already used by /dashboard/parquet-analysis. The AWS
 * dataset panels below intentionally avoid demo revenue assumptions and show
 * billing dimensions that exist in Cost Explorer/CUR/FOCUS data.
 */
export default function FinOpsPage() {
  const alertQuery = useSpendVelocityAlert();
  const seriesQuery = useSpendVelocitySeries();
  const parquetQuery = useParquetAnalysis({ source: "local" });
  const forecastQuery = useForecastAnomaly();
  const teamQuery = useTeamAttribution();
  const spendUpdatedAt = Math.max(alertQuery.dataUpdatedAt, seriesQuery.dataUpdatedAt);
  const spendFetching = alertQuery.isFetching || seriesQuery.isFetching;

  return (
    <div className="mx-auto w-full max-w-[1400px]">
      <div className="stage py-1">
        <div className="eyebrow">FinOps intelligence</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">
          AWS spend operations, live from FOCUS
        </h1>
        <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-ink-faint">
          Realtime spend velocity, AWS cost export breakdowns, unit-cost signals, forecast drift, and tag attribution in one operating view.
        </p>
      </div>

      <div className="mt-4 grid gap-5 xl:grid-cols-2">
        <Panel
          eyebrow="SpendShield-lite - live"
          title="Spend Velocity Guard"
          subtitle="Windowed rate-ratio + CUSUM change-point confirmation. Estimated from usage metrics, never a billed figure; that lag is the whole point."
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
          eyebrow="AWS FOCUS export"
          title="AWS Cost Dataset"
          subtitle="AWS FOCUS Parquet grouped by ServiceName, billing account, RegionName, and usage/SKU columns. This follows the real AWS export shape instead of demo margin data."
          aside={
            <RealtimePanelAside
              isFetching={parquetQuery.isFetching}
              updatedAt={parquetQuery.dataUpdatedAt}
              statusLabel="AWS FOCUS"
              onRefresh={() => {
                void parquetQuery.refetch();
              }}
            />
          }
          delay={220}
        >
          {parquetQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : parquetQuery.isError ? (
            <p className="text-[12.5px] text-destructive">
              {isApiError(parquetQuery.error)
                ? parquetQuery.error.message
                : "Could not load the latest AWS FOCUS Parquet analysis."}
            </p>
          ) : parquetQuery.data ? (
            <AwsFocusCostPanelBody analysis={parquetQuery.data} />
          ) : null}
        </Panel>
      </div>

      <div className="mt-5">
        <Panel
          eyebrow="AWS FOCUS export - unit signals"
          title="AWS Unit Cost Signals"
          subtitle="Realtime operational unit metrics from the same AWS dataset: cost per resource, cost per row, effective cost, top ResourceId lines, and S3 freshness."
          aside={
            <RealtimePanelAside
              isFetching={parquetQuery.isFetching}
              updatedAt={parquetQuery.dataUpdatedAt}
              statusLabel="AWS FOCUS"
              onRefresh={() => {
                void parquetQuery.refetch();
              }}
            />
          }
          delay={340}
        >
          {parquetQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : parquetQuery.isError ? (
            <p className="text-[12.5px] text-destructive">
              {isApiError(parquetQuery.error)
                ? parquetQuery.error.message
                : "Could not load the latest AWS FOCUS Parquet analysis."}
            </p>
          ) : parquetQuery.data ? (
            <AwsFocusUnitSignalsPanelBody analysis={parquetQuery.data} />
          ) : null}
        </Panel>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel
          eyebrow="Forecast Anomaly Guard"
          title="Daily Cost Forecast"
          subtitle="Walk-forward: each day is forecast using only prior days, then compared to what actually happened; never a lookahead-biased fit."
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
          subtitle="Grouped by whatever tag key identifies a team at your org, case-insensitive; untagged spend is its own line item, never hidden."
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
