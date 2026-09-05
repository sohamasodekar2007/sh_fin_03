"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Money, formatMoneyParts } from "@/components/Money";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { deriveServiceLabel, resourceIdFromArn, type Proposal, type ResourceStatus } from "@/lib/cloudcare-data";
import { isApiError } from "@/lib/api";
import { useResourceDetail } from "@/lib/queries";

/**
 * Everything known about one resource, opened from a click on any row in
 * ResourcesTable.tsx. Backed by GET /v1/resources/{resource_id}
 * (apps/api/routers/resources.py) — real FOCUS cost rows joined on
 * ResourceId (not a re-derived estimate), the CloudWatch-derived
 * utilization metric if one has been collected, and proposals whose
 * resource_arn ends in this id. `resourceId === null` means closed;
 * passing a fresh id while already open just re-points the same sheet.
 */

const STATUS_COLOR: Record<ResourceStatus, string> = {
  Healthy: "var(--mint)",
  Idle: "var(--signal)",
  "Over-provisioned": "var(--ember)",
  "At-risk": "var(--destructive)",
};

const RISK_COLOR: Record<string, string> = {
  low: "var(--mint)",
  medium: "var(--signal)",
  high: "var(--ember)",
  critical: "var(--destructive)",
};

function ProposalRow({ proposal }: { proposal: Proposal }) {
  return (
    <div className="rounded-md border border-hairline p-3">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="num text-[11.5px] text-foreground">{deriveServiceLabel(proposal.template_id)}</span>
        <span className="text-[11px] text-ink-faint">{proposal.action_type.replace(/_/g, " ")}</span>
        <Badge
          variant="outline"
          className="text-[10px] uppercase"
          style={{ color: RISK_COLOR[proposal.risk_level] ?? "var(--ink-faint)", borderColor: `color-mix(in oklab, ${RISK_COLOR[proposal.risk_level] ?? "var(--ink-faint)"} 40%, transparent)` }}
        >
          {proposal.risk_level}
        </Badge>
        <Badge variant="secondary" className="text-[10px]">
          {proposal.status.replace(/_/g, " ")}
        </Badge>
      </div>
      <p className="mb-1 text-[11.5px] text-ink-dim">
        Expected savings: <Money value={Number(proposal.expected_monthly_savings) || 0} inline usdOnly />/mo
      </p>
      <p className="text-[11px] leading-relaxed text-ink-faint">{proposal.rationale}</p>
    </div>
  );
}

export function ResourceDetailSheet({
  resourceId,
  onOpenChange,
}: {
  resourceId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const detailQuery = useResourceDetail(resourceId);

  return (
    <Sheet open={resourceId != null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl md:max-w-2xl">
        {resourceId == null ? null : detailQuery.isLoading ? (
          <div className="space-y-3 pt-6">
            <Skeleton className="h-7 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="mt-4 h-[300px] w-full" />
          </div>
        ) : detailQuery.isError ? (
          <div className="pt-10 text-center">
            <p className="text-[13px] text-destructive">
              {isApiError(detailQuery.error) ? detailQuery.error.message : "Could not load this resource."}
            </p>
          </div>
        ) : detailQuery.data ? (
          <ResourceDetailBody detail={detailQuery.data} />
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function ResourceDetailBody({ detail }: { detail: import("@/lib/cloudcare-data").ResourceDetail }) {
  const { resource, metric, cost_trend, charge_breakdown, focus_dataset_id, focus_row_count, related_proposals } = detail;
  const tagEntries = Object.entries(resource.tags ?? {});

  return (
    <div>
      <SheetHeader>
        <SheetTitle className="num">{resource.id}</SheetTitle>
        <SheetDescription>
          <span className="capitalize">{resource.resource_type?.replace(/_/g, " ") ?? resource.type}</span>
          {" · "}
          <span className="uppercase">{resource.provider ?? "—"}</span>
          {" · "}
          <span className="capitalize">{resource.environment}</span>
          {" · "}
          {resource.region}
        </SheetDescription>
      </SheetHeader>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge
          variant="outline"
          style={{ color: STATUS_COLOR[resource.status], borderColor: `color-mix(in oklab, ${STATUS_COLOR[resource.status]} 40%, transparent)` }}
        >
          {resource.status}
        </Badge>
        {resource.state && <Badge variant="outline">{resource.state}</Badge>}
        {resource.owner && <Badge variant="secondary">owner: {resource.owner}</Badge>}
      </div>

      <Tabs defaultValue="overview" className="mt-5">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="cost">Cost</TabsTrigger>
          <TabsTrigger value="proposals">Proposals ({related_proposals.length})</TabsTrigger>
          <TabsTrigger value="tags">Tags ({tagEntries.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="eyebrow">Monthly cost</p>
              <Money value={resource.monthly_cost_usd} className="text-[16px]" />
            </div>
            <div>
              <p className="eyebrow">Cost source</p>
              <p className="text-[13px] text-ink-dim">
                {resource.focus_version ? `FOCUS ${resource.focus_version}` : "—"} · {focus_row_count} row{focus_row_count === 1 ? "" : "s"}
              </p>
            </div>
            {resource.resource_type === "ec2_instance" && (
              <>
                <div>
                  <p className="eyebrow">CPU p95 / avg</p>
                  <p className="num text-[13px] text-ink-dim">
                    {resource.cpu_p95.toFixed(2)}% / {metric?.cpu_avg != null ? `${metric.cpu_avg.toFixed(2)}%` : "—"}
                  </p>
                </div>
                <div>
                  <p className="eyebrow">Memory p95</p>
                  <p className="num text-[13px] text-ink-dim">{metric?.mem_p95 != null ? `${metric.mem_p95.toFixed(2)}%` : "—"}</p>
                </div>
              </>
            )}
          </div>
          {metric && (
            <p className="text-[11px] text-ink-faint">
              Utilization window: {new Date(metric.window_start).toLocaleString()} → {new Date(metric.window_end).toLocaleString()} (
              {metric.sample_count} samples)
            </p>
          )}
          {focus_dataset_id && (
            <p className="num text-[11px] text-ink-faint">FOCUS dataset: {focus_dataset_id}</p>
          )}
        </TabsContent>

        <TabsContent value="cost" className="mt-4">
          {cost_trend.length === 0 ? (
            <p className="py-6 text-center text-[12.5px] text-ink-faint">No FOCUS cost rows reference this resource yet.</p>
          ) : (
            <>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={cost_trend} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="resource-cost-fill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--signal)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="var(--signal)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} tickFormatter={(d: string) => d.slice(5)} />
                    <YAxis tick={{ fontSize: 10, fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip
                      formatter={(value: number) => [formatMoneyParts(value).usd, "billed cost"]}
                      contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "var(--hairline)", background: "var(--surface)" }}
                    />
                    <Area type="monotone" dataKey="billed_cost" stroke="var(--signal)" strokeWidth={2} fill="url(#resource-cost-fill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div className="mt-4 space-y-1.5">
                <p className="eyebrow mb-1">Charge breakdown</p>
                {charge_breakdown.map((item) => (
                  <div key={`${item.charge_description}-${item.charge_category}`} className="flex items-center justify-between text-[11.5px]">
                    <span className="text-ink-dim">
                      {item.charge_description} <span className="text-ink-faint">({item.charge_category})</span>
                    </span>
                    <span className="num text-foreground">
                      <Money value={item.billed_cost} inline usdOnly /> <span className="text-ink-faint">· {item.row_count}</span>
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="proposals" className="mt-4 space-y-2">
          {related_proposals.length === 0 ? (
            <p className="py-6 text-center text-[12.5px] text-ink-faint">No proposals reference this resource.</p>
          ) : (
            related_proposals.map((p) => <ProposalRow key={p.proposal_id} proposal={p} />)
          )}
        </TabsContent>

        <TabsContent value="tags" className="mt-4">
          {tagEntries.length === 0 ? (
            <p className="py-6 text-center text-[12.5px] text-ink-faint">No tags on this resource.</p>
          ) : (
            <div className="space-y-1">
              {tagEntries.map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-[11.5px]">
                  <span className="num text-ink-dim">{key}</span>
                  <span className="text-foreground">{value || "—"}</span>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// Re-exported so callers deriving a resource id from a proposal's
// resource_arn (e.g. to link a proposal row back into this sheet) don't
// need a second import from cloudcare-data.ts just for this one helper.
export { resourceIdFromArn };
