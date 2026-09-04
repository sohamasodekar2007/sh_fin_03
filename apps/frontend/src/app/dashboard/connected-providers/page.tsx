"use client";

import Link from "next/link";
import { Cloud, Plus } from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCloudAccounts } from "@/lib/queries";

const STATUS_COLOR: Record<string, string> = {
  validated: "var(--mint)",
  pending: "var(--signal)",
  failed: "var(--destructive)",
};

export default function ConnectedProvidersPage() {
  const accountsQuery = useCloudAccounts();
  const accounts = accountsQuery.data ?? [];

  return (
    <div className="mx-auto w-full max-w-[1200px]">
      <div className="stage flex flex-wrap items-start justify-between gap-3 py-1">
        <div>
          <div className="eyebrow">Cloud accounts</div>
          <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">Connected providers</h1>
        </div>
        <Button asChild size="sm">
          <Link href="/onboarding">
            <Plus className="size-4" /> Connect another provider
          </Link>
        </Button>
      </div>

      <div className="mt-4">
        <Panel title="Every account this tenant has attempted to connect" delay={140}>
          {accountsQuery.isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28 w-full" />
              ))}
            </div>
          ) : accounts.length === 0 ? (
            <p className="py-8 text-center text-[12.5px] text-ink-faint">
              No cloud accounts connected yet —{" "}
              <Link className="underline" href="/onboarding">
                connect one from onboarding
              </Link>
              .
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {accounts.map((a) => (
                <div key={`${a.provider}-${a.account_id}`} className="rounded-md border border-border/70 bg-surface-raised/60 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Cloud className="size-4 text-ink-faint" />
                      <span className="text-[13px] font-medium uppercase text-foreground">{a.provider}</span>
                    </div>
                    <Badge
                      variant="outline"
                      className="text-[10px] capitalize"
                      style={{ color: STATUS_COLOR[a.status] ?? "var(--ink-faint)", borderColor: `color-mix(in oklab, ${STATUS_COLOR[a.status] ?? "var(--ink-faint)"} 40%, transparent)` }}
                    >
                      {a.status}
                    </Badge>
                  </div>
                  <div className="num mt-2.5 truncate text-[11.5px] text-ink-dim" title={a.account_id}>
                    {a.account_id}
                  </div>
                  <div className="mt-1 text-[11px] text-ink-faint">Region: {a.region}</div>
                  <div className="mt-2.5 flex items-center gap-1.5 text-[11px]" style={{ color: a.connected ? "var(--mint)" : "var(--ink-faint)" }}>
                    <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: a.connected ? "var(--mint)" : "var(--graphite)" }} />
                    {a.connected ? "Connected" : "Not connected"}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
