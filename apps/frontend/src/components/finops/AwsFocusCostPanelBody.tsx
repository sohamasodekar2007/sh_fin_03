"use client";

import type { ReactNode } from "react";
import { Database, Server, type LucideIcon } from "lucide-react";

import { Money } from "@/components/Money";
import { Badge } from "@/components/ui/badge";
import type { ParquetAnalysis, ParquetBreakdownItem } from "@/lib/cloudcare-data";

function pct(value: number, denominator: number) {
  if (!Number.isFinite(value) || !Number.isFinite(denominator) || denominator <= 0) return "0%";
  return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 }).format(Math.abs(value) / denominator);
}

function BreakdownList({ label, items }: { label: string; items: ParquetBreakdownItem[] }) {
  const max = Math.max(...items.map((item) => Math.abs(item.cost_usd)), 1);
  const denominator = Math.max(
    items.reduce((sum, item) => sum + Math.abs(item.cost_usd), 0),
    1,
  );
  return (
    <div className="min-w-0 rounded-md border border-hairline bg-surface-raised p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="eyebrow">{label}</div>
        <Badge variant="outline">{items.length} shown</Badge>
      </div>
      <div className="space-y-3">
        {items.slice(0, 5).map((item) => (
          <div key={`${label}-${item.name}`} className="min-w-0">
            <div className="flex items-center justify-between gap-3 text-[12px]">
              <span className="truncate font-medium text-foreground" title={item.name}>
                {item.name}
              </span>
              <span className="num shrink-0 text-ink-dim">{pct(item.cost_usd, denominator)}</span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-signal" style={{ width: `${Math.max(4, (Math.abs(item.cost_usd) / max) * 100)}%` }} />
              </div>
              <span className="num w-[78px] shrink-0 text-right text-[11.5px] text-foreground">
                <Money value={item.cost_usd} inline usdOnly />
              </span>
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="text-[12px] text-ink-faint">No populated AWS column for this grouping in the latest export.</p>}
      </div>
    </div>
  );
}

function SummaryStat({ label, value, icon: Icon }: { label: string; value: ReactNode; icon: LucideIcon }) {
  return (
    <div className="rounded-md border border-hairline bg-surface-raised p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <Icon className="size-4 text-ink-faint" />
      </div>
      <div className="num mt-2 text-[1.35rem] font-semibold text-foreground">{value}</div>
    </div>
  );
}

export function AwsFocusCostPanelBody({ analysis }: { analysis: ParquetAnalysis }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryStat label="Billed cost" icon={Database} value={<Money value={analysis.summary.billed_cost_usd} inline usdOnly />} />
        <SummaryStat label="Services" icon={Server} value={analysis.summary.distinct_services.toLocaleString()} />
        <SummaryStat label="Resources" icon={Server} value={analysis.summary.distinct_resources.toLocaleString()} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <BreakdownList label="ServiceName" items={analysis.breakdowns.by_service} />
        <BreakdownList label="Billing account" items={analysis.breakdowns.by_billing_account ?? []} />
        <BreakdownList label="RegionName" items={analysis.breakdowns.by_region} />
        <BreakdownList label="Usage / SKU meter" items={analysis.breakdowns.by_usage ?? []} />
      </div>
    </div>
  );
}
