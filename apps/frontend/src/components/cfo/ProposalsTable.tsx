"use client";

import { useMemo, useState } from "react";

import { Money } from "@/components/Money";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  deriveProvider,
  deriveServiceLabel,
  resourceIdFromArn,
  type Proposal,
  type ProposalStatus,
} from "@/lib/cloudcare-data";

/**
 * Ported from the template's ArAgingTable.tsx — same aging-rail-style
 * summary strip, sort/filter control row and sticky-header scrollable
 * table structure. Renamed and remapped: this is CloudCare's proposal
 * table, not accounts receivable. Columns: resource, provider, service,
 * environment, monthly cost, finding (template_id), proposed action,
 * savings, risk, confidence, status. Row click selects into
 * VariancePanel, same interaction as the template's invoice rows opening
 * VariancePanel there.
 */

const RISK_COLOR: Record<string, string> = {
  low: "var(--mint)",
  medium: "var(--signal)",
  high: "var(--ember)",
  critical: "var(--destructive)",
};

const STATUS_COLOR: Record<ProposalStatus, string> = {
  proposed: "var(--ink-faint)",
  pending_approval: "var(--signal)",
  approved: "var(--mint)",
  queued_for_execution: "var(--signal)",
  rejected: "var(--graphite)",
  blocked: "var(--destructive)",
  executed: "var(--mint)",
  verified: "var(--mint)",
};

type SortKey = "cost" | "savings" | "risk" | "confidence";

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function decisionDate(proposal: Proposal) {
  return proposal.approved_at ?? proposal.rejected_at ?? null;
}

interface Props {
  proposals: Proposal[];
  selectedId: string | null;
  onSelect: (proposal: Proposal) => void;
}

export function ProposalsTable({ proposals, selectedId, onSelect }: Props) {
  const [sort, setSort] = useState<SortKey>("savings");
  const [providerFilter, setProviderFilter] = useState<string>("all");
  const [environmentFilter, setEnvironmentFilter] = useState<string>("all");

  const providers = useMemo(() => Array.from(new Set(proposals.map((p) => deriveProvider(p.resource_arn)))), [proposals]);
  const environments = useMemo(() => Array.from(new Set(proposals.map((p) => p.environment))), [proposals]);

  const rows = useMemo(() => {
    let r = [...proposals];
    if (providerFilter !== "all") r = r.filter((p) => deriveProvider(p.resource_arn) === providerFilter);
    if (environmentFilter !== "all") r = r.filter((p) => p.environment === environmentFilter);
    const riskOrder: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };
    r.sort((a, b) => {
      if (sort === "cost") return (Number(b.cost_current_monthly) || 0) - (Number(a.cost_current_monthly) || 0);
      if (sort === "savings") return (Number(b.expected_monthly_savings) || 0) - (Number(a.expected_monthly_savings) || 0);
      if (sort === "risk") return (riskOrder[b.risk_level] ?? 0) - (riskOrder[a.risk_level] ?? 0);
      return (b.confidence_score ?? b.confidence ?? 0) - (a.confidence_score ?? a.confidence ?? 0);
    });
    return r;
  }, [proposals, providerFilter, environmentFilter, sort]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={providerFilter} onValueChange={setProviderFilter}>
            <SelectTrigger className="h-8 w-[120px] text-[12px]">
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
        </div>
        <div role="group" aria-label="Sort proposals" className="flex items-center gap-1">
          <span className="eyebrow" aria-hidden>Sort</span>
          {(
            [
              ["savings", "Savings"],
              ["cost", "Cost"],
              ["risk", "Risk"],
              ["confidence", "Confidence"],
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

      <div className="mt-3 max-h-[430px] overflow-y-auto">
        <Table>
          <TableCaption>{rows.length} proposal{rows.length === 1 ? "" : "s"}.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Resource</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Service</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead className="text-right">Monthly cost</TableHead>
              <TableHead>Finding</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Decision</TableHead>
              <TableHead className="text-right">Savings</TableHead>
              <TableHead>Risk</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((p) => {
              const confidence = p.confidence_score ?? p.confidence;
              const selected = selectedId === p.proposal_id;
              return (
                <TableRow
                  key={p.proposal_id}
                  onClick={() => onSelect(p)}
                  aria-selected={selected}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSelect(p);
                  }}
                  className="cursor-pointer transition-colors hover:bg-secondary/40 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
                  style={selected ? { background: "color-mix(in oklab, var(--signal) 8%, transparent)" } : undefined}
                >
                  <TableCell className="num max-w-[160px] truncate text-[11.5px]" title={p.resource_arn}>
                    {resourceIdFromArn(p.resource_arn)}
                  </TableCell>
                  <TableCell className="text-[11.5px] uppercase text-ink-dim">{deriveProvider(p.resource_arn)}</TableCell>
                  <TableCell className="text-[11.5px] text-ink-dim">{deriveServiceLabel(p.template_id)}</TableCell>
                  <TableCell className="text-[11.5px] capitalize text-ink-dim">{p.environment}</TableCell>
                  <TableCell className="text-right">
                    <Money value={Number(p.cost_current_monthly)} compact inline className="text-[11.5px]" />
                  </TableCell>
                  <TableCell className="max-w-[140px] truncate text-[11px] text-ink-faint" title={p.template_id}>
                    {p.template_id}
                  </TableCell>
                  <TableCell className="text-[11.5px] capitalize text-ink-dim">{p.action_type.replace(/_/g, " ")}</TableCell>
                  <TableCell className="num whitespace-nowrap text-[11px] text-ink-faint">{formatDate(p.created_at)}</TableCell>
                  <TableCell className="num whitespace-nowrap text-[11px] text-ink-faint">{formatDate(decisionDate(p))}</TableCell>
                  <TableCell className="text-right">
                    <Money value={Number(p.expected_monthly_savings)} compact inline className="text-[11.5px]" style={{ color: "var(--mint)" }} />
                  </TableCell>
                  <TableCell>
                    <span
                      className="num inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[9.5px] uppercase tracking-wider"
                      style={{
                        color: RISK_COLOR[p.risk_level],
                        background: `color-mix(in oklab, ${RISK_COLOR[p.risk_level]} 12%, var(--surface))`,
                        border: `1px solid color-mix(in oklab, ${RISK_COLOR[p.risk_level]} 32%, transparent)`,
                      }}
                    >
                      {p.risk_level}
                    </span>
                  </TableCell>
                  <TableCell className="num text-right text-[11.5px] text-ink-dim">
                    {typeof confidence === "number" ? `${Math.round(confidence * 100)}%` : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className="whitespace-nowrap text-[10px] capitalize"
                      style={{ color: STATUS_COLOR[p.status], borderColor: `color-mix(in oklab, ${STATUS_COLOR[p.status]} 40%, transparent)` }}
                    >
                      {p.status.replace(/_/g, " ")}
                    </Badge>
                  </TableCell>
                </TableRow>
              );
            })}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={13} className="py-8 text-center text-[12.5px] text-ink-faint">
                  No proposals match this filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
