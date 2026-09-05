"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { ProposalsTable } from "@/components/cfo/ProposalsTable";
import { VariancePanel } from "@/components/cfo/VariancePanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { deriveProvider, deriveServiceLabel, type Proposal } from "@/lib/cloudcare-data";
import { useProposals } from "@/lib/queries";

function formatLastUpdated(updatedAt: number) {
  if (!updatedAt) return "Waiting";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(updatedAt));
}

function statusMessage(error: unknown) {
  if (!error) return "Proposal sync failed.";
  if (error instanceof Error) return error.message;
  if (typeof error === "object" && "message" in error) return String((error as { message?: unknown }).message);
  return "Proposal sync failed.";
}

function csvValue(value: unknown) {
  if (value === null || value === undefined) return "";
  const raw = typeof value === "object" ? JSON.stringify(value) : String(value);
  const safe = /^[=+\-@]/.test(raw) ? `\t${raw}` : raw;
  return `"${safe.replace(/"/g, '""')}"`;
}

function proposalDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function exportProposalsCsv(proposals: Proposal[]) {
  const headers = [
    "proposal_id",
    "created_at",
    "approved_at",
    "rejected_at",
    "status",
    "execution_id",
    "execution_status",
    "execution_mode",
    "provider",
    "service",
    "resource_arn",
    "environment",
    "action_type",
    "template_id",
    "risk_level",
    "confidence",
    "cost_current_monthly",
    "expected_monthly_savings",
    "savings_annual",
    "approved_by",
    "rejected_by",
    "rejection_reason",
    "actual_aws_call_made",
    "rationale",
  ];
  const rows = proposals.map((proposal) => [
    proposal.proposal_id,
    proposalDate(proposal.created_at),
    proposalDate(proposal.approved_at),
    proposalDate(proposal.rejected_at),
    proposal.status,
    proposal.execution_id,
    proposal.execution_status,
    proposal.execution_mode,
    deriveProvider(proposal.resource_arn),
    deriveServiceLabel(proposal.template_id),
    proposal.resource_arn,
    proposal.environment,
    proposal.action_type,
    proposal.template_id,
    proposal.risk_level,
    proposal.confidence_score ?? proposal.confidence,
    proposal.cost_current_monthly,
    proposal.expected_monthly_savings,
    proposal.savings_annual,
    proposal.approved_by,
    proposal.rejected_by,
    proposal.rejection_reason,
    proposal.actual_aws_call_made,
    proposal.rationale,
  ]);
  const csv = [headers, ...rows].map((row) => row.map(csvValue).join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `cloudcare-proposals-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function ProposalsLiveAside({
  isFetching,
  isError,
  updatedAt,
  proposalCount,
  onRefresh,
  onExport,
}: {
  isFetching: boolean;
  isError: boolean;
  updatedAt: number;
  proposalCount: number;
  onRefresh: () => void;
  onExport: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2" aria-live="polite">
      <Badge
        variant="outline"
        className="gap-1.5 whitespace-nowrap text-[11px]"
        style={{ borderColor: "color-mix(in oklab, var(--mint) 38%, transparent)" }}
      >
        <span
          className="size-1.5 rounded-full bg-[var(--mint)]"
          style={{ boxShadow: "0 0 0 3px color-mix(in oklab, var(--mint) 18%, transparent)" }}
        />
        {isError ? "Sync retrying" : isFetching ? "Refreshing" : "Live 2s"}
      </Badge>
      <span className="hidden text-right text-[11px] leading-tight text-ink-faint sm:block">
        <span className="block font-medium text-foreground">{isFetching ? "Updating" : "Last synced"}</span>
        <span className="num">{formatLastUpdated(updatedAt)}</span>
      </span>
      <Button size="sm" variant="outline" onClick={onRefresh} disabled={isFetching}>
        <RefreshCw className={isFetching ? "size-3.5 animate-spin" : "size-3.5"} />
        Refresh
      </Button>
      <Button size="sm" variant="outline" onClick={onExport} disabled={proposalCount === 0}>
        <Download className="size-3.5" />
        CSV
      </Button>
    </div>
  );
}

export default function ProposalsPage() {
  const queryClient = useQueryClient();
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);

  const proposalsQuery = useProposals({ refetchInterval: 2_000 });
  const proposals = useMemo(() => proposalsQuery.data ?? [], [proposalsQuery.data]);
  const selectedProposal = useMemo(
    () => proposals.find((p) => p.proposal_id === selectedProposalId) ?? null,
    [proposals, selectedProposalId],
  );
  const totals = useMemo(
    () => ({
      pending: proposals.filter((p) => p.status === "pending_approval").length,
      approved: proposals.filter((p) => p.status === "approved").length,
      executed: proposals.filter((p) => p.status === "executed" || p.status === "verified").length,
      blocked: proposals.filter((p) => p.status === "blocked" || p.status === "rejected").length,
    }),
    [proposals],
  );

  useEffect(() => {
    if (selectedProposalId && proposalsQuery.data && !selectedProposal) {
      setSelectedProposalId(null);
    }
  }, [proposalsQuery.data, selectedProposal, selectedProposalId]);

  function handleDecided() {
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ["proposals"] }),
      queryClient.invalidateQueries({ queryKey: ["resources"] }),
      queryClient.invalidateQueries({ queryKey: ["cost-summary"] }),
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] }),
    ]);
  }

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage py-1">
        <div className="eyebrow">Proposals</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">Every flagged resource</h1>
      </div>

      <div className="mt-4">
        <Panel
          title="All proposals"
          subtitle="Live from approvals every 2 seconds. Click a row for supervisor evidence and execution state."
          aside={
            <ProposalsLiveAside
              isFetching={proposalsQuery.isFetching}
              isError={proposalsQuery.isError}
              updatedAt={proposalsQuery.dataUpdatedAt}
              proposalCount={proposals.length}
              onRefresh={() => void proposalsQuery.refetch()}
              onExport={() => exportProposalsCsv(proposals)}
            />
          }
          delay={140}
        >
          {proposalsQuery.isError && (
            <div className="mb-3 rounded border border-destructive/30 bg-destructive/5 px-3 py-2 text-[12px] text-destructive">
              {statusMessage(proposalsQuery.error)}
            </div>
          )}
          {!proposalsQuery.isLoading && (
            <div className="mb-3 grid gap-2 sm:grid-cols-4">
              <div className="rounded border bg-secondary/20 px-3 py-2">
                <div className="eyebrow">Pending</div>
                <div className="num mt-1 text-lg font-semibold">{totals.pending}</div>
              </div>
              <div className="rounded border bg-secondary/20 px-3 py-2">
                <div className="eyebrow">Approved</div>
                <div className="num mt-1 text-lg font-semibold">{totals.approved}</div>
              </div>
              <div className="rounded border bg-secondary/20 px-3 py-2">
                <div className="eyebrow">Executed</div>
                <div className="num mt-1 text-lg font-semibold">{totals.executed}</div>
              </div>
              <div className="rounded border bg-secondary/20 px-3 py-2">
                <div className="eyebrow">Closed / blocked</div>
                <div className="num mt-1 text-lg font-semibold">{totals.blocked}</div>
              </div>
            </div>
          )}
          {proposalsQuery.isLoading ? (
            <Skeleton className="h-[420px] w-full" />
          ) : (
            <ProposalsTable proposals={proposals} selectedId={selectedProposalId} onSelect={(p) => setSelectedProposalId(p.proposal_id)} />
          )}
        </Panel>
      </div>

      <VariancePanel proposal={selectedProposal} onClose={() => setSelectedProposalId(null)} onDecided={handleDecided} />
    </div>
  );
}
