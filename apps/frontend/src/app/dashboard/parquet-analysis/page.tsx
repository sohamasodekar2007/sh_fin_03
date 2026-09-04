"use client";

import { useMemo } from "react";
import { ArrowUpRight, Clock, Database, FileJson, RefreshCw, Server, UploadCloud } from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api";
import type { ParquetBreakdownItem } from "@/lib/cloudcare-data";
import { useParquetAnalysis } from "@/lib/queries";

function money(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "$0.00";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function text(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Stat({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Database }) {
  return (
    <div className="min-w-0 rounded-md border border-hairline bg-surface-raised p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <Icon className="size-4 shrink-0 text-ink-faint" />
      </div>
      <div className="num mt-2 truncate text-[1.35rem] font-semibold leading-tight text-foreground">{value}</div>
    </div>
  );
}

function Breakdown({ title, items }: { title: string; items: ParquetBreakdownItem[] }) {
  const max = Math.max(...items.map((item) => item.cost_usd), 1);
  return (
    <Panel title={title} bodyClassName="px-5 pb-5 sm:px-6 sm:pb-6" headerClassName="p-5 pb-3 sm:p-6 sm:pb-3">
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.name} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
            <div className="min-w-0">
              <div className="flex items-center justify-between gap-3 text-[12.5px]">
                <span className="truncate font-medium text-foreground">{item.name}</span>
                <span className="num shrink-0 text-ink-dim">{money(item.cost_usd)}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-signal" style={{ width: `${Math.max(5, (item.cost_usd / max) * 100)}%` }} />
              </div>
            </div>
            <Badge variant="outline">{item.rows} rows</Badge>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export default function ParquetAnalysisPage() {
  const query = useParquetAnalysis();
  const data = query.data;

  const previewColumns = useMemo(() => {
    if (!data) return [];
    const priority = ["ServiceName", "ServiceCategory", "RegionName", "ResourceId", "ResourceName", "BilledCost", "EffectiveCost", "ChargeCategory"];
    const names = data.schema.map((column) => column.name);
    return [...priority.filter((name) => names.includes(name)), ...names.filter((name) => !priority.includes(name))].slice(0, 18);
  }, [data]);

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage py-1">
        <div className="eyebrow">AWS FOCUS parquet converter</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">
          Parquet Analysis
        </h1>
        <p className="mt-1.5 max-w-3xl text-[12.5px] leading-relaxed text-ink-faint">
          Inspect the AWS cost export, convert it into dashboard-ready summaries, and stage the hourly S3 rewrite target.
        </p>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel
          title="Automatic S3 source"
          subtitle="Reads the newest .parquet object from the configured S3 bucket and prefix."
          bodyClassName="p-5 pt-0 sm:p-6 sm:pt-0"
          aside={
            <Button size="sm" variant="outline" onClick={() => query.refetch()} disabled={query.isFetching}>
              <RefreshCw className={`size-4 ${query.isFetching ? "animate-spin" : ""}`} /> Refresh
            </Button>
          }
        >
          {data ? (
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-md border border-hairline bg-surface-raised p-3">
                <div className="eyebrow">Bucket</div>
                <div className="mt-2 truncate font-mono text-[12px] text-foreground">{data.file.bucket}</div>
              </div>
              <div className="rounded-md border border-hairline bg-surface-raised p-3">
                <div className="eyebrow">Latest key</div>
                <div className="mt-2 truncate font-mono text-[12px] text-foreground" title={data.file.key}>
                  {data.file.key}
                </div>
              </div>
              <div className="rounded-md border border-hairline bg-surface-raised p-3">
                <div className="eyebrow">Source</div>
                <div className="mt-2 truncate font-mono text-[12px] text-foreground" title={data.file.uri}>
                  {data.file.uri}
                </div>
              </div>
            </div>
          ) : (
            <Skeleton className="h-24 w-full" />
          )}
          {query.error && (
            <div className="mt-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-[12.5px] text-destructive">
              {isApiError(query.error) ? query.error.message : "Could not load Parquet analysis."}
            </div>
          )}
        </Panel>

        <Panel title="Hourly S3 rewrite" bodyClassName="p-5 pt-0 sm:p-6 sm:pt-0">
          {data ? (
            <div className="space-y-3 text-[12.5px]">
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink-faint">Cadence</span>
                <span className="num text-foreground">{data.converter.cadence_minutes} min</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink-faint">Automatic refresh</span>
                <Badge variant="secondary">
                  <Clock className="mr-1 inline size-3.5" /> On
                </Badge>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink-faint">S3 target</span>
                <Badge variant={data.converter.s3_configured ? "secondary" : "outline"}>
                  {data.converter.s3_configured ? "Configured" : "Missing bucket"}
                </Badge>
              </div>
              <div className="rounded-md bg-muted p-3 font-mono text-[11px] leading-relaxed text-ink-dim">
                {data.converter.target_uri ?? "FOCUS_EXPORT_S3_BUCKET not set"}
              </div>
              <div className="flex items-start gap-2 rounded-md border border-hairline p-3 text-ink-faint">
                <UploadCloud className="mt-0.5 size-4 shrink-0" />
                <span>The backend scheduler rewrites this summary artifact every hour from S3. The page never uploads a local file.</span>
              </div>
            </div>
          ) : (
            <Skeleton className="h-40 w-full" />
          )}
        </Panel>
      </div>

      {query.isLoading && <Skeleton className="mt-4 h-[520px] w-full" />}

      {data && (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Stat label="Billed cost" value={money(data.summary.billed_cost_usd)} icon={Server} />
            <Stat label="Effective cost" value={money(data.summary.effective_cost_usd)} icon={ArrowUpRight} />
            <Stat label="Rows" value={data.summary.rows.toLocaleString()} icon={Database} />
            <Stat label="Columns" value={data.summary.columns.toLocaleString()} icon={FileJson} />
            <Stat label="Resources" value={data.summary.distinct_resources.toLocaleString()} icon={Server} />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Breakdown title="Cost by service" items={data.breakdowns.by_service} />
            <Breakdown title="Cost by region" items={data.breakdowns.by_region} />
            <Breakdown title="Cost by category" items={data.breakdowns.by_category} />
            <Breakdown title="Cost by charge category" items={data.breakdowns.by_charge_category} />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
            <Panel title="Schema" subtitle={`${data.schema.length} columns from ${data.file.name}`} bodyClassName="px-5 pb-5 sm:px-6 sm:pb-6">
              <div className="max-h-[560px] overflow-auto rounded-md border border-hairline">
                <table className="w-full text-left text-[12px]">
                  <thead className="sticky top-0 bg-surface-raised text-ink-faint">
                    <tr>
                      <th className="px-3 py-2 font-medium">Column</th>
                      <th className="px-3 py-2 font-medium">Type</th>
                      <th className="px-3 py-2 font-medium">Null</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.schema.map((column) => (
                      <tr key={column.name} className="border-t border-hairline">
                        <td className="px-3 py-2 font-mono text-foreground">{column.name}</td>
                        <td className="px-3 py-2 font-mono text-ink-dim">{column.type}</td>
                        <td className="px-3 py-2 text-ink-faint">{column.nullable ? "yes" : "no"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Row preview" subtitle="First 50 rows with the AWS cost columns first." bodyClassName="px-5 pb-5 sm:px-6 sm:pb-6">
              <div className="max-h-[560px] overflow-auto rounded-md border border-hairline">
                <table className="min-w-[1120px] text-left text-[12px]">
                  <thead className="sticky top-0 bg-surface-raised text-ink-faint">
                    <tr>
                      {previewColumns.map((column) => (
                        <th key={column} className="whitespace-nowrap px-3 py-2 font-medium">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.sample_rows.map((row, index) => (
                      <tr key={index} className="border-t border-hairline">
                        {previewColumns.map((column) => (
                          <td key={column} className="max-w-[260px] truncate px-3 py-2 font-mono text-ink-dim" title={text(row[column])}>
                            {text(row[column])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
