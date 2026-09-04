"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getAuthHeaders, getDemoSession } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type Outcome = "checking" | "redirecting" | "ok" | "error";

export default function ApproveTokenPage() {
  const router = useRouter();
  const params = useParams();
  const token = Array.isArray(params?.token) ? params.token[0] : (params?.token as string);

  const [outcome, setOutcome] = useState<Outcome>("checking");
  const [message, setMessage] = useState("");
  const [action, setAction] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;

    const session = getDemoSession();
    if (!session) {
      setOutcome("redirecting");
      router.replace(`/login?returnTo=${encodeURIComponent(`/approve/${token}`)}`);
      return;
    }

    (async () => {
      try {
        const res = await fetch(`${BASE_URL}/v1/approvals/email/${token}`, {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json", ...getAuthHeaders() },
        });
        const data = await res.json();
        setAction(data.action ?? null);
        setMessage(data.message || (res.ok ? "Done." : "This link could not be processed."));
        setOutcome(res.ok && data.ok !== false ? "ok" : "error");
      } catch (err: any) {
        setMessage(err?.message || "Could not reach the CloudCare API.");
        setOutcome("error");
      }
    })();
  }, [token, router]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg px-6">
      <div className="w-full max-w-sm">
        <Link href="/" className="flex items-center justify-center gap-2.5 font-display font-bold text-xl text-ink mb-8">
          <span className="w-8 h-8 rounded-[10px] bg-gradient-to-br from-brandBlue to-brandTeal inline-block" />
          CloudCare
        </Link>

        <div className="bg-surface border border-line rounded-lg2 shadow-soft p-8 text-center">
          {outcome === "checking" && (
            <>
              <h1 className="font-display text-xl font-semibold text-ink mb-1">Checking your link…</h1>
              <p className="text-sm text-inkSoft">One moment.</p>
            </>
          )}

          {outcome === "redirecting" && (
            <>
              <h1 className="font-display text-xl font-semibold text-ink mb-1">Please log in</h1>
              <p className="text-sm text-inkSoft">
                Taking you to login — you'll be brought back here to finish confirming this proposal.
              </p>
            </>
          )}

          {outcome === "ok" && (
            <>
              <h1 className="font-display text-xl font-semibold text-ink mb-1">
                {action === "approve" ? "Proposal approved" : action === "reject" ? "Proposal rejected" : "Confirmed"}
              </h1>
              <p className="text-sm text-inkSoft mb-6">{message}</p>
              <Link
                href="/dashboard"
                className="inline-flex items-center justify-center rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white hover:-translate-y-0.5 hover:shadow-[0_10px_20px_-8px_rgba(16,34,46,0.4)] transition-all"
              >
                Go to dashboard
              </Link>
            </>
          )}

          {outcome === "error" && (
            <>
              <h1 className="font-display text-xl font-semibold text-ink mb-1">Link unavailable</h1>
              <p className="text-sm text-inkSoft mb-6">{message}</p>
              <Link
                href="/dashboard"
                className="inline-flex items-center justify-center rounded-full border-[1.5px] border-line px-6 py-3 text-sm font-semibold text-inkSoft hover:bg-bg transition-all"
              >
                Go to dashboard
              </Link>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
