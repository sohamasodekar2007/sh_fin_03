"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Money } from "@/components/Money";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, isApiError } from "@/lib/api";
import type { ApprovalCard } from "@/lib/cloudcare-data";

/**
 * Approve/Reject here are real actions against the same
 * POST /v1/approvals/{id}/approve|reject endpoints VariancePanel.tsx uses —
 * the chat turn that produced this card (services/chat/tools.py's
 * approve_proposal tool) never mutates anything itself, only this click does.
 */
export function ApprovalCardView({ card, onDecided }: { card: ApprovalCard; onDecided?: () => void }) {
  const [status, setStatus] = useState<"pending" | "approved" | "rejected">("pending");
  const [loading, setLoading] = useState<"approve" | "reject" | null>(null);

  async function decide(action: "approve" | "reject") {
    setLoading(action);
    try {
      await api.post(`/v1/approvals/${card.proposal_id}/${action}`, action === "reject" ? { reason: "Rejected from CloudCareAI" } : undefined);
      setStatus(action === "approve" ? "approved" : "rejected");
      toast.success(action === "approve" ? "Proposal approved." : "Proposal rejected.");
      onDecided?.();
    } catch (err) {
      toast.error(isApiError(err) ? err.message : `Could not ${action} this proposal.`);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="mt-2 rounded-md border border-border/70 bg-surface-raised/60 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow" style={{ color: "var(--signal)" }}>
          Requires your approval
        </span>
        <Badge variant="outline" className="text-[10px] capitalize">
          {card.risk} risk · {Math.round(card.confidence * 100)}% confidence
        </Badge>
      </div>
      <div className="num mt-2 truncate text-[11px] text-ink-faint" title={card.target}>
        {card.target}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="text-[13px] capitalize text-foreground">{card.action.replace(/_/g, " ")}</span>
        <Money value={card.savings} compact inline className="text-[12px]" style={{ color: "var(--mint)" }} />
        <span className="text-[11px] text-ink-faint">/mo savings</span>
      </div>

      {status === "pending" ? (
        <div className="mt-3 flex gap-2">
          <Button size="sm" onClick={() => decide("approve")} disabled={loading !== null} className="flex-1">
            {loading === "approve" ? "Approving…" : "Approve"}
          </Button>
          <Button size="sm" variant="outline" onClick={() => decide("reject")} disabled={loading !== null} className="flex-1">
            {loading === "reject" ? "Rejecting…" : "Reject"}
          </Button>
        </div>
      ) : (
        <div className="mt-3 text-[12px]" style={{ color: status === "approved" ? "var(--mint)" : "var(--destructive)" }}>
          {status === "approved" ? "✓ Approved — sent to the Executor Agent." : "✕ Rejected."}
        </div>
      )}
    </div>
  );
}
