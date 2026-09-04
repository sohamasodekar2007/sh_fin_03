"use client";

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Panel } from "@/components/cfo/Panel";
import { ProposalsTable } from "@/components/cfo/ProposalsTable";
import { VariancePanel } from "@/components/cfo/VariancePanel";
import { Skeleton } from "@/components/ui/skeleton";
import { useProposals } from "@/lib/queries";

export default function ProposalsPage() {
  const queryClient = useQueryClient();
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);

  const proposalsQuery = useProposals();
  const proposals = useMemo(() => proposalsQuery.data ?? [], [proposalsQuery.data]);
  const selectedProposal = useMemo(
    () => proposals.find((p) => p.proposal_id === selectedProposalId) ?? null,
    [proposals, selectedProposalId],
  );

  function handleDecided() {
    queryClient.invalidateQueries({ queryKey: ["proposals"] });
  }

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage py-1">
        <div className="eyebrow">Proposals</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">Every flagged resource</h1>
      </div>

      <div className="mt-4">
        <Panel title="All proposals" subtitle="Sortable, filterable by provider and environment. Click a row for supervisor evidence." delay={140}>
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
