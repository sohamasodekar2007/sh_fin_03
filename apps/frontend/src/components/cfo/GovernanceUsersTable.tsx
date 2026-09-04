"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { IAMUserDetail } from "@/lib/cloudcare-data";

// Same rotation-hygiene baseline as services/collector/iam_collector.py's
// STALE_KEY_AGE_DAYS — kept in sync manually since it's just a display
// threshold, not a value the frontend fetches from the backend.
const STALE_KEY_AGE_DAYS = 90;

export function GovernanceUsersTable({ users }: { users: IAMUserDetail[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (users.length === 0) {
    return <p className="py-8 text-center text-[12.5px] text-ink-faint">No IAM users found (or not yet accessible).</p>;
  }

  return (
    <div className="divide-y divide-border/60">
      {users.map((user) => {
        const isOpen = expanded === user.user_name;
        const stale = user.access_key_age_days !== null && user.access_key_age_days >= STALE_KEY_AGE_DAYS;
        return (
          <div key={user.user_name}>
            <button
              type="button"
              onClick={() => setExpanded(isOpen ? null : user.user_name)}
              aria-expanded={isOpen}
              className="flex w-full flex-wrap items-center gap-3 py-3 text-left transition-colors hover:bg-secondary/30 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-medium text-foreground">{user.user_name}</span>
                  {stale && (
                    <span
                      className="num rounded-sm px-1.5 py-0.5 text-[9px] uppercase tracking-wide"
                      style={{ color: "var(--destructive)", background: "color-mix(in oklab, var(--destructive) 12%, transparent)" }}
                    >
                      key {user.access_key_age_days}d old
                    </span>
                  )}
                </div>
                <div className="num mt-0.5 truncate text-[10.5px] text-ink-faint">{user.arn}</div>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                {user.groups.map((g) => (
                  <Badge key={g} variant="outline" className="text-[10px]">
                    {g}
                  </Badge>
                ))}
                <span className="num text-[10.5px] text-ink-faint">{user.policies.length} polic{user.policies.length === 1 ? "y" : "ies"}</span>
              </div>
            </button>

            {isOpen && (
              <div className="space-y-2 pb-3 pl-1">
                {user.policies.length === 0 && <p className="text-[11.5px] text-ink-faint">No attached or inline policies.</p>}
                {user.policies.map((policy, i) => (
                  <div key={`${policy.name}-${i}`} className="rounded-md border border-border/60 bg-surface-raised/60 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[12px] font-medium text-foreground">{policy.name}</span>
                      <Badge variant="outline" className="text-[9px] uppercase">
                        {policy.type}
                      </Badge>
                    </div>
                    {policy.arn && <div className="num mt-1 truncate text-[10px] text-ink-faint">{policy.arn}</div>}
                    {policy.document && (
                      <pre className="num mt-2 max-h-56 overflow-auto rounded bg-surface p-2 text-[10px] leading-relaxed text-ink-dim">
                        {JSON.stringify(policy.document, null, 2)}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
