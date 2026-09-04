"use client";

import { ShieldAlert, ShieldCheck } from "lucide-react";

import { GovernanceUsersTable } from "@/components/cfo/GovernanceUsersTable";
import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIamGovernance } from "@/lib/queries";

function OverviewBadge({ ok, label, unknownLabel }: { ok: boolean | null; label: string; unknownLabel: string }) {
  if (ok === null) {
    return (
      <Badge variant="outline" className="gap-1.5 text-[11px]">
        {unknownLabel}
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className="gap-1.5 text-[11px]"
      style={{ color: ok ? "var(--mint)" : "var(--destructive)", borderColor: `color-mix(in oklab, ${ok ? "var(--mint)" : "var(--destructive)"} 40%, transparent)` }}
    >
      {ok ? <ShieldCheck className="size-3" /> : <ShieldAlert className="size-3" />}
      {label}
    </Badge>
  );
}

export default function GovernancePage() {
  const govQuery = useIamGovernance();
  const data = govQuery.data;

  return (
    <div className="mx-auto w-full max-w-[1200px]">
      <div className="stage py-1">
        <div className="eyebrow">Identity & access</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">IAM & Governance</h1>
        <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-ink-faint">
          Every real IAM user, their actual groups and policies, root-account posture, and who created what — sourced
          directly from IAM and CloudTrail, not inferred.
        </p>
      </div>

      <div className="mt-4">
        <Panel title="Account overview" delay={100}>
          {govQuery.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : data ? (
            <div className="flex flex-wrap items-center gap-2">
              <OverviewBadge
                ok={data.account.root_mfa_enabled === null ? null : data.account.root_mfa_enabled}
                label="Root MFA enabled"
                unknownLabel="Root MFA — unknown"
              />
              <OverviewBadge
                ok={data.account.root_access_keys_present === null ? null : !data.account.root_access_keys_present}
                label="No root access keys"
                unknownLabel="Root access keys — unknown"
              />
              <OverviewBadge
                ok={data.account.password_policy_configured}
                label="Password policy configured"
                unknownLabel="Password policy — unknown"
              />
              {data.account.alias && (
                <span className="num text-[11px] text-ink-faint">
                  {data.account.alias} · {data.account.account_id}
                </span>
              )}
              {data.errors.account && (
                <span className="text-[11px] text-destructive">Account overview: {data.errors.account}</span>
              )}
            </div>
          ) : null}
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Users & permissions" delay={220}>
          {govQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : data?.errors.users ? (
            <p className="text-[12.5px] text-destructive">Could not list users: {data.errors.users}</p>
          ) : (
            <GovernanceUsersTable users={data?.users ?? []} />
          )}
        </Panel>
      </div>

      <div className="mt-5">
        <Panel
          title="Who created what"
          subtitle={`Sourced from CloudTrail — covers the trailing ${data?.resource_creators_lookback_days ?? 90} days only; anything older shows as not attributable, never a guess.`}
          delay={340}
        >
          {govQuery.isLoading ? (
            <Skeleton className="h-[220px] w-full" />
          ) : data?.errors.resource_creators ? (
            <p className="text-[12.5px] text-destructive">Could not read CloudTrail: {data.errors.resource_creators}</p>
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              <Table>
                <TableCaption>{(data?.resource_creators ?? []).length} resource-creation events.</TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead>Resource</TableHead>
                    <TableHead>Event</TableHead>
                    <TableHead>Created by</TableHead>
                    <TableHead>When</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(data?.resource_creators ?? []).map((c, i) => (
                    <TableRow key={`${c.resource_id}-${i}`}>
                      <TableCell className="num max-w-[200px] truncate text-[11.5px]" title={c.resource_id}>
                        {c.resource_id}
                      </TableCell>
                      <TableCell className="text-[11.5px] text-ink-dim">{c.event_name}</TableCell>
                      <TableCell className="num max-w-[220px] truncate text-[11.5px] text-ink-dim" title={c.principal_arn ?? undefined}>
                        {c.principal_name ?? "—"}
                      </TableCell>
                      <TableCell className="num text-[11px] text-ink-faint">{new Date(c.event_time).toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                  {(data?.resource_creators ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={4} className="py-8 text-center text-[12.5px] text-ink-faint">
                        No resource-creation events in the lookback window.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
