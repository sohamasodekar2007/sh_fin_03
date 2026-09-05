"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Gauge } from "lucide-react";
import { toast } from "sonner";

import { Money } from "@/components/Money";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, isApiError } from "@/lib/api";
import { deriveProvider, deriveServiceLabel, resourceIdFromArn, type Proposal } from "@/lib/cloudcare-data";

/**
 * Ported from the template's VariancePanel.tsx — same slide-over
 * mechanics (focus trap, Escape to close, backdrop, transform transition)
 * unchanged. Remapped from budget-variance commentary to Supervisor
 * evidence (services/supervisor/service.py's score_proposal): confidence
 * and risk as labelled bars, the evidence list with FOCUS column
 * provenance, and the Decision agent's plain-English rationale. Approve/
 * reject are real actions against POST /v1/approvals/{id}/approve|reject
 * — not decorative, this is the actual human-in-the-loop control surface.
 */

interface Props {
  proposal: Proposal | null;
  onClose: () => void;
  onDecided: () => void;
}

function ScoreBar({ label, value, color }: { label: string; value: number | undefined; color: string }) {
  const pct = typeof value === "number" ? Math.round(Math.min(1, Math.max(0, value)) * 100) : null;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="eyebrow">{label}</span>
        <span className="num text-[11px] text-ink-dim">{pct === null ? "—" : `${pct}%`}</span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${pct ?? 0}%`, background: color }} />
      </div>
    </div>
  );
}

export function VariancePanel({ proposal, onClose, onDecided }: Props) {
  const open = proposal !== null;
  const panelRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const returnRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const [rejectReason, setRejectReason] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [loading, setLoading] = useState<"approve" | "reject" | null>(null);

  useEffect(() => {
    setShowRejectForm(false);
    setRejectReason("");
  }, [proposal?.proposal_id]);

  useEffect(() => {
    if (!open) return;
    returnRef.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const root = panelRef.current;
      if (!root) return;
      const items = Array.from(
        root.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])'),
      ).filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      returnRef.current?.focus?.();
    };
  }, [open]);

  async function handleApprove() {
    if (!proposal) return;
    setLoading("approve");
    try {
      await api.post(`/v1/approvals/${proposal.proposal_id}/approve`);
      toast.success("Proposal approved.");
      onDecided();
      onClose();
    } catch (err) {
      toast.error(isApiError(err) ? err.message : "Could not approve this proposal.");
    } finally {
      setLoading(null);
    }
  }

  async function handleReject() {
    if (!proposal) return;
    setLoading("reject");
    try {
      await api.post(`/v1/approvals/${proposal.proposal_id}/reject`, { reason: rejectReason });
      toast.success("Proposal rejected.");
      onDecided();
      onClose();
    } catch (err) {
      toast.error(isApiError(err) ? err.message : "Could not reject this proposal.");
    } finally {
      setLoading(null);
    }
  }

  const canDecide = proposal?.status === "pending_approval";

  return (
    <>
      <div
        onClick={onClose}
        className="fixed inset-0 z-40 bg-background/60 backdrop-blur-[2px] transition-opacity duration-300"
        style={{ opacity: open ? 1 : 0, pointerEvents: open ? "auto" : "none" }}
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal={open}
        aria-label={proposal ? `Evidence for ${proposal.action_type} on ${resourceIdFromArn(proposal.resource_arn)}` : undefined}
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[440px] flex-col border-l border-hairline bg-surface shadow-2xl transition-transform duration-[420ms]"
        style={{ transform: open ? "translateX(0)" : "translateX(100%)", transitionTimingFunction: "cubic-bezier(0.22,1,0.36,1)" }}
        aria-hidden={!open}
        {...(open ? {} : { inert: true })}
      >
        {proposal && (
          <>
            <header className="flex items-start justify-between gap-4 border-b border-border/70 p-6">
              <div className="min-w-0">
                <div className="eyebrow">
                  {deriveProvider(proposal.resource_arn).toUpperCase()} · {deriveServiceLabel(proposal.template_id, proposal.resource_arn, proposal.resource_type)}
                </div>
                <h3 className="mt-1.5 text-xl font-semibold leading-tight text-foreground">
                  {proposal.action_type.replace(/_/g, " ")}
                </h3>
                <div className="num mt-2 truncate text-[11px] text-ink-faint">{resourceIdFromArn(proposal.resource_arn)}</div>
              </div>
              <button
                ref={closeRef}
                onClick={onClose}
                aria-label="Close evidence panel"
                className="-mr-1 -mt-1 shrink-0 rounded p-1.5 text-ink-faint transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
              >
                <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                  <path d="M3 3l9 9M12 3l-9 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </header>

            <div className="flex-1 overflow-y-auto p-6">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-md border border-border/70 bg-surface-raised/60 p-3">
                  <div className="eyebrow">Monthly savings</div>
                  <Money value={Number(proposal.expected_monthly_savings)} compact className="mt-1.5 text-sm font-medium" style={{ color: "var(--mint)" }} />
                </div>
                <div className="rounded-md border border-border/70 bg-surface-raised/60 p-3">
                  <div className="eyebrow">Status</div>
                  <div className="mt-1.5">
                    <Badge variant="outline" className="capitalize">{proposal.status.replace(/_/g, " ")}</Badge>
                  </div>
                </div>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-4">
                <ScoreBar label="Confidence" value={proposal.confidence_score ?? proposal.confidence} color="var(--mint)" />
                <ScoreBar label="Risk" value={proposal.risk_score} color="var(--ember)" />
              </div>

              <div className="num mt-3 text-[10.5px] text-ink-faint">
                Risk level: {proposal.risk_level} · Environment: {proposal.environment} · Policy: {proposal.policy_outcome ?? "—"}
              </div>

              <div className="mt-6">
                <div className="eyebrow">Plain-English read</div>
                <p className="mt-2.5 text-[13.5px] leading-relaxed text-foreground/85">
                  {proposal.rationale_plain_english || proposal.rationale}
                </p>
                {proposal.risk_notes && (
                  <p className="mt-2 text-[12px] leading-relaxed text-ink-faint">{proposal.risk_notes}</p>
                )}
              </div>

              <div className="mt-6">
                <div className="eyebrow">Dependency facts</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(proposal.dependency_facts?.length ? proposal.dependency_facts : ["No dependency facts recorded"]).map((fact) => (
                    <Badge key={fact} variant="outline" className="max-w-full break-all text-[10px]">
                      {fact}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="mt-7">
                <div className="eyebrow">Evidence</div>
                <div className="mt-2.5 divide-y divide-border/60">
                  {proposal.evidence.length === 0 && (
                    <p className="py-2.5 text-[12px] text-ink-faint">No structured evidence recorded for this proposal.</p>
                  )}
                  {proposal.evidence.map((e, i) => (
                    <div key={`${e.metric}-${i}`} className="flex items-baseline justify-between gap-4 py-2.5">
                      <div className="min-w-0">
                        <span className="text-[12.5px] text-ink-dim">{e.metric}</span>
                        <div className="num text-[10px] text-ink-faint">{e.window_days}d window</div>
                      </div>
                      <span className="num shrink-0 text-[12px] text-foreground">{e.value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {canDecide && (
                <div className="mt-7 border-t border-border/70 pt-5">
                  {!showRejectForm ? (
                    <div className="flex gap-2">
                      <Button size="sm" variant="destructive" onClick={handleApprove} disabled={loading !== null} className="flex-1">
                        {loading === "approve" ? <Gauge className="size-3.5 animate-spin" /> : <CheckCircle2 className="size-3.5" />}
                        {loading === "approve" ? "Approving" : "Approve"}
                      </Button>
                      <Button variant="outline" onClick={() => setShowRejectForm(true)} disabled={loading !== null} className="flex-1">
                        Reject
                      </Button>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-2">
                      <Textarea
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                        placeholder="Reason (optional)…"
                        rows={2}
                        className="text-[12.5px]"
                      />
                      <div className="flex gap-2">
                        <Button variant="destructive" onClick={handleReject} disabled={loading !== null} className="flex-1">
                          {loading === "reject" ? "Rejecting…" : "Confirm reject"}
                        </Button>
                        <Button variant="ghost" onClick={() => setShowRejectForm(false)} disabled={loading !== null}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
