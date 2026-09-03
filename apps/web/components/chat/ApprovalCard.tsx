"use client";

import { useState } from "react";
import { getAuthHeaders } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface ApprovalCardPayload {
  type: "approval_card";
  proposal_id: string;
  resource_id: string;
  action_template: string;
  rationale: string;
  estimated_monthly_savings_usd: number;
  risk_score: number;
  risk_reason: string;
}

// Generative UI approval card (spec section 5) — rendered inline in the
// chat bubble whenever the Supervisor Agent routed a proposal to
// REQUIRE_HUMAN. Approve/Reject post straight to the Executor via
// POST /v1/recommendations/{proposal_id}/decision, authenticated with the
// same NextAuth session bearer token as every other backend call.
export default function ApprovalCard({ payload }: { payload: ApprovalCardPayload }) {
  const [status, setStatus] = useState<"pending" | "approved" | "rejected" | "error">("pending");
  const [loading, setLoading] = useState(false);

  const decide = async (decision: "approve" | "reject") => {
    setLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/v1/recommendations/${payload.proposal_id}/decision`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify({ decision }),
      });
      if (!res.ok) throw new Error(await res.text());
      setStatus(decision === "approve" ? "approved" : "rejected");
    } catch {
      setStatus("error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-2 bg-surface border border-line rounded-lg2 shadow-card p-4 max-w-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-bold uppercase tracking-wide text-brandAmber">Requires your approval</span>
        <span className="text-[11px] font-mono text-inkFaint">risk {payload.risk_score.toFixed(2)}</span>
      </div>
      <p className="font-mono text-[13px] font-semibold text-ink mb-1">{payload.resource_id}</p>
      <p className="text-[12.5px] text-inkSoft mb-2">
        {payload.action_template} — est. <span className="font-semibold text-ink">${payload.estimated_monthly_savings_usd.toFixed(2)}/mo</span> savings
      </p>
      <p className="text-[12px] text-inkFaint mb-3">{payload.rationale}</p>
      <p className="text-[11px] text-inkFaint mb-3 italic">{payload.risk_reason}</p>

      {status === "pending" && (
        <div className="flex gap-2">
          <button
            onClick={() => decide("approve")}
            disabled={loading}
            className="flex-1 rounded-full bg-brandTeal px-4 py-2 text-xs font-semibold text-white hover:opacity-90 transition-all disabled:opacity-50"
          >
            Approve
          </button>
          <button
            onClick={() => decide("reject")}
            disabled={loading}
            className="flex-1 rounded-full bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:opacity-90 transition-all disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
      {status === "approved" && <p className="text-xs font-semibold text-brandTeal">✓ Approved — sent to the Executor Agent.</p>}
      {status === "rejected" && <p className="text-xs font-semibold text-red-600">✕ Rejected.</p>}
      {status === "error" && <p className="text-xs font-semibold text-red-600">Something went wrong — try again.</p>}
    </div>
  );
}
