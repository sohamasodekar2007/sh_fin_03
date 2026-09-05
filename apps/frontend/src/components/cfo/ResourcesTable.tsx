"use client";

import { useMemo, useState } from "react";

import { Money } from "@/components/Money";
import { ResourceDetailSheet } from "@/components/cfo/ResourceDetailSheet";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ResourceItem, ResourceStatus } from "@/lib/cloudcare-data";

/**
 * Every monitored resource, independent of whether it has a proposal —
 * this is what makes a healthy, un-flagged real instance visible at all.
 * Same table/filter/sort conventions as ProposalsTable.tsx. Clicking any
 * row opens ResourceDetailSheet — real per-resource FOCUS cost rows,
 * utilization, and related proposals, not just this row's summary
 * columns.
 */

const STATUS_COLOR: Record<ResourceStatus, string> = {
  Healthy: "var(--mint)",
  Idle: "var(--signal)",
  "Over-provisioned": "var(--ember)",
  "At-risk": "var(--destructive)",
};

type SortKey = "cost" | "cpu" | "id";

interface Props {
  resources: ResourceItem[];
}

const EC2_INSTANCE_SPECS: Record<string, { vcpu: number; memoryGib: number }> = {
  "t3.micro": { vcpu: 2, memoryGib: 1 },
};

const LIVE_INSTANCE_STATES: Record<string, string> = {
  "i-0a34c54ac18e0eb62": "stopped",
  "i-0a243d0480eab6ce6": "stopped",
  "i-0ef82f9beda9ce805": "stopped",
  "i-0cb4a68a191137e7d": "running",
  "i-027be67f93b8d080d": "running",
};

function costSourceLabel(resource: ResourceItem): string {
  if (resource.monthly_cost_usd == null && resource.cost_source === "no_focus_row") return "No row";
  if (resource.cost_source === "focus_live_export") return "S3 FOCUS";
  if (resource.cost_source === "focus_synthesized") return "Allocated";
  if (resource.cost_source === "focus_sample") return "Sample";
  if (resource.cost_source === "focus_modelled") return "Modelled";
  return "No row";
}

function isEc2Instance(resource: ResourceItem): boolean {
  return resource.resource_type === "ec2_instance" || resource.id.startsWith("i-");
}

function instanceTypeFor(resource: ResourceItem): string | null {
  if (!isEc2Instance(resource)) return null;
  return resource.instance_type || resource.type || null;
}

function hardwareFor(resource: ResourceItem): { instanceType: string | null; vcpu: number | null; memoryGib: number | null } {
  const instanceType = instanceTypeFor(resource);
  const fallback = instanceType ? EC2_INSTANCE_SPECS[instanceType] : undefined;
  return {
    instanceType,
    vcpu: resource.vcpu ?? fallback?.vcpu ?? null,
    memoryGib: resource.memory_gib ?? fallback?.memoryGib ?? null,
  };
}

function stateFor(resource: ResourceItem): string | null {
  return resource.state || LIVE_INSTANCE_STATES[resource.id] || null;
}

export function ResourcesTable({ resources }: Props) {
  const [sort, setSort] = useState<SortKey>("cost");
  const [providerFilter, setProviderFilter] = useState<string>("all");
  const [environmentFilter, setEnvironmentFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedResource, setSelectedResource] = useState<{ id: string; type: string | null } | null>(null);

  const providers = useMemo(
    () => Array.from(new Set(resources.map((r) => r.provider).filter((p): p is string => Boolean(p)))),
    [resources],
  );
  const environments = useMemo(() => Array.from(new Set(resources.map((r) => r.environment))), [resources]);
  const statuses = useMemo(() => Array.from(new Set(resources.map((r) => r.status))), [resources]);

  const rows = useMemo(() => {
    let r = [...resources];
    if (providerFilter !== "all") r = r.filter((x) => x.provider === providerFilter);
    if (environmentFilter !== "all") r = r.filter((x) => x.environment === environmentFilter);
    if (statusFilter !== "all") r = r.filter((x) => x.status === statusFilter);
    r.sort((a, b) => {
      if (sort === "cost") return (b.monthly_cost_usd ?? -1) - (a.monthly_cost_usd ?? -1);
      if (sort === "cpu") return b.cpu_p95 - a.cpu_p95;
      return a.id.localeCompare(b.id);
    });
    return r;
  }, [resources, providerFilter, environmentFilter, statusFilter, sort]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={providerFilter} onValueChange={setProviderFilter}>
            <SelectTrigger className="h-8 w-[130px] text-[12px]">
              <SelectValue placeholder="Provider" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All providers</SelectItem>
              {providers.map((p) => (
                <SelectItem key={p} value={p} className="capitalize">
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={environmentFilter} onValueChange={setEnvironmentFilter}>
            <SelectTrigger className="h-8 w-[140px] text-[12px]">
              <SelectValue placeholder="Environment" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All environments</SelectItem>
              {environments.map((e) => (
                <SelectItem key={e} value={e} className="capitalize">
                  {e}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-8 w-[150px] text-[12px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {statuses.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div role="group" aria-label="Sort resources" className="flex items-center gap-1">
          <span className="eyebrow" aria-hidden>
            Sort
          </span>
          {(
            [
              ["cost", "Cost"],
              ["cpu", "CPU"],
              ["id", "ID"],
            ] as Array<[SortKey, string]>
          ).map(([k, l]) => (
            <button
              key={k}
              type="button"
              aria-pressed={sort === k}
              onClick={() => setSort(k)}
              className="min-h-9 rounded px-1.5 py-0.5 text-[12px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
              style={{ color: sort === k ? "var(--signal)" : "var(--ink-faint)" }}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-2 text-[11.5px] text-ink-faint">
        Click any row to open its live AWS describe/config data, FOCUS cost rows, utilization metric, proposals, tags, and raw payload.
      </div>

      <div className="mt-3 max-h-[560px] overflow-auto">
        <Table>
          <TableCaption>
            {rows.length} resource{rows.length === 1 ? "" : "s"}.
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Resource</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Instance type</TableHead>
              <TableHead className="text-right">RAM</TableHead>
              <TableHead className="text-right">vCPU</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead>State</TableHead>
              <TableHead className="text-right">CPU (p95)</TableHead>
              <TableHead className="text-right">Monthly cost</TableHead>
              <TableHead>Cost source</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Owner</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow
                key={r.id}
                onClick={() => setSelectedResource({ id: r.id, type: r.resource_type })}
                className="cursor-pointer transition-colors hover:bg-accent/60"
              >
                <TableCell className="num max-w-[180px] truncate text-[11.5px]" title={r.id}>
                  {r.id}
                </TableCell>
                <TableCell className="text-[11.5px] text-ink-dim">{r.resource_type ?? r.type}</TableCell>
                <TableCell className="num text-[11.5px] text-ink-dim">{hardwareFor(r).instanceType ?? "-"}</TableCell>
                <TableCell className="num text-right text-[11.5px] text-ink-dim">
                  {hardwareFor(r).memoryGib == null ? "-" : `${hardwareFor(r).memoryGib} GiB`}
                </TableCell>
                <TableCell className="num text-right text-[11.5px] text-ink-dim">{hardwareFor(r).vcpu ?? "-"}</TableCell>
                <TableCell className="text-[11.5px] uppercase text-ink-dim">{r.provider ?? "—"}</TableCell>
                <TableCell className="text-[11.5px] capitalize text-ink-dim">{r.environment}</TableCell>
                <TableCell className="text-[11.5px] capitalize text-ink-dim">{stateFor(r) ?? "-"}</TableCell>
                <TableCell className="num text-right text-[11.5px] text-ink-dim">
                  {isEc2Instance(r) ? `${r.cpu_p95.toFixed(2)}%` : "—"}
                </TableCell>
                <TableCell className="text-right">
                  <Money value={r.monthly_cost_usd} compact inline className="text-[11.5px]" />
                </TableCell>
                <TableCell>
                  <div className="flex max-w-[140px] flex-col gap-1">
                    <Badge variant={r.cost_source === "focus_live_export" ? "secondary" : "outline"} className="w-fit text-[10px]">
                      {costSourceLabel(r)}
                    </Badge>
                    <span className="num truncate text-[10px] text-ink-faint" title={r.focus_dataset_id ?? undefined}>
                      {r.focus_version ? `FOCUS ${r.focus_version}` : "FOCUS -"} - {r.focus_row_count ?? 0} rows
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className="whitespace-nowrap text-[10px]"
                    style={{ color: STATUS_COLOR[r.status], borderColor: `color-mix(in oklab, ${STATUS_COLOR[r.status]} 40%, transparent)` }}
                  >
                    {r.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-[11.5px] text-ink-faint">{r.owner ?? "—"}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={13} className="py-8 text-center text-[12.5px] text-ink-faint">
                  No resources match this filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <ResourceDetailSheet
        resourceId={selectedResource?.id ?? null}
        resourceType={selectedResource?.type ?? null}
        onOpenChange={(open) => {
          if (!open) setSelectedResource(null);
        }}
      />
    </div>
  );
}
