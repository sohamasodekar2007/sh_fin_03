"use client";

import type { ReactNode } from "react";
import { Clock, Database, FileJson, Server, type LucideIcon } from "lucide-react";

import { Money } from "@/components/Money";
import { Badge } from "@/components/ui/badge";
import type { ParquetAnalysis, ParquetBreakdownItem } from "@/lib/cloudcare-data";

function dateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function unitCost(total: number, denominator: number) {
  if (!Number.isFinite(total) || !Number.isFinite(denominator) || denominator <= 0) return 0;
  return total / denominator;
}

function UnitStat({ label, value, icon: Icon }: { label: string; value: ReactNode; icon: LucideIcon }) {
  return (
    <div className="rounded-md border border-hairline bg-surface-raised p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <Icon className="size-4 text-ink-faint" />
      </div>
      <div className="num mt-2 truncate text-[1.2rem] font-semibold leading-tight text-foreground">{value}</div>
    </div>
  );
}

function TopResourceRows({ items }: { items: ParquetBreakdownItem[] }) {
  return (
    <div className="overflow-hidden rounded-md border border-hairline">
      <table className="w-full text-left text-[12px]">
        <thead className="bg-surface-raised text-ink-faint">
          <tr>
            <th className="px-3 py-2 font-medium">ResourceId</th>
            <th className="px-3 py-2 text-right font-medium">BilledCost</th>
            <th className="px-3 py-2 text-right font-medium">Rows</th>
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 6).map((item) => (
            <tr key={item.name} className="border-t border-hairline">
              <td className="max-w-[360px] truncate px-3 py-2 font-mono text-foreground" title={item.name}>
                {item.name}
              </td>
              <td className="num px-3 py-2 text-right text-ink-dim">
                <Money value={item.cost_usd} inline usdOnly />
              </td>
              <td className="num px-3 py-2 text-right text-ink-faint">{item.rows.toLocaleString()}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr className="border-t border-hairline">
              <td colSpan={3} className="px-3 py-4 text-ink-faint">
                ResourceId is not populated in the latest AWS export.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function AwsFocusUnitSignalsPanelBody({ analysis }: { analysis: ParquetAnalysis }) {
  const total = analysis.summary.billed_cost_usd;
  const savingsPct =
    analysis.summary.list_cost_usd > 0 ? (analysis.summary.savings_vs_list_usd / analysis.summary.list_cost_usd) * 100 : 0;
  const sourceLabel = analysis.file.source === "s3" ? "S3 live" : "Local AWS";

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <UnitStat label="Cost / resource" icon={Server} value={<Money value={unitCost(total, analysis.summary.distinct_resources)} inline usdOnly />} />
        <UnitStat label="Cost / row" icon={Database} value={<Money value={unitCost(total, analysis.summary.rows)} inline usdOnly />} />
        <UnitStat label="Effective cost" icon={FileJson} value={<Money value={analysis.summary.effective_cost_usd} inline usdOnly />} />
        <UnitStat label="S3 modified" icon={Clock} value={dateTime(analysis.file.last_modified)} />
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_290px]">
        <TopResourceRows items={analysis.breakdowns.by_resource ?? []} />
        <div className="rounded-md border border-hairline bg-surface-raised p-3 text-[12.5px]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="eyebrow">FOCUS readiness</span>
            <Badge variant="secondary">{sourceLabel}</Badge>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-ink-faint">Rows</span>
              <span className="num text-foreground">{analysis.summary.rows.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-ink-faint">Columns</span>
              <span className="num text-foreground">{analysis.summary.columns.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-ink-faint">List savings</span>
              <span className="num text-foreground">{savingsPct.toFixed(1)}%</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-ink-faint">Generated</span>
              <span className="num text-foreground">{dateTime(analysis.generated_at)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
