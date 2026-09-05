"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  ChevronDown,
  ExternalLink,
  FileJson,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { GovernanceUsersTable } from "@/components/cfo/GovernanceUsersTable";
import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { IAMGovernanceOverview, ResourceCreator } from "@/lib/cloudcare-data";
import { useIamGovernance } from "@/lib/queries";

interface CreatorGroup {
  principal: string;
  principalArn: string | null;
  events: ResourceCreator[];
}

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
      style={{
        color: ok ? "var(--mint)" : "var(--destructive)",
        borderColor: `color-mix(in oklab, ${ok ? "var(--mint)" : "var(--destructive)"} 40%, transparent)`,
      }}
    >
      {ok ? <ShieldCheck className="size-3" /> : <ShieldAlert className="size-3" />}
      {label}
    </Badge>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function eventTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function shortPrincipal(value: string | null | undefined) {
  if (!value) return "unknown-principal";
  const parts = value.split("/");
  return parts[parts.length - 1] || value;
}

function groupCreators(creators: ResourceCreator[]): CreatorGroup[] {
  const grouped = new Map<string, CreatorGroup>();
  for (const event of creators) {
    const principal = event.principal_name || shortPrincipal(event.principal_arn);
    const key = event.principal_arn || principal;
    const existing = grouped.get(key);
    if (existing) {
      existing.events.push(event);
    } else {
      grouped.set(key, { principal, principalArn: event.principal_arn, events: [event] });
    }
  }
  return Array.from(grouped.values())
    .map((group) => ({
      ...group,
      events: [...group.events].sort((a, b) => eventTime(b.event_time) - eventTime(a.event_time)),
    }))
    .sort((a, b) => b.events.length - a.events.length || a.principal.localeCompare(b.principal));
}

function matchesGroup(group: CreatorGroup, search: string) {
  const query = search.trim().toLowerCase();
  if (!query) return true;
  const text = [
    group.principal,
    group.principalArn ?? "",
    ...group.events.flatMap((event) => [event.resource_id, event.event_name, event.event_time]),
  ]
    .join(" ")
    .toLowerCase();
  return text.includes(query);
}

function createdResourceType(eventName: string) {
  const map: Record<string, string> = {
    RunInstances: "EC2 instance",
    CreateBucket: "S3 bucket",
    CreateFunction20150331: "Lambda function",
    CreateDBInstance: "RDS database",
    CreateTable: "DynamoDB table",
    CreateDistribution: "CloudFront distribution",
    CreateVpc: "VPC",
    CreateVolume: "EBS volume",
  };
  return map[eventName] ?? eventName;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[8px] border border-border bg-background px-3 py-2.5">
      <div className="text-[10px] font-medium uppercase text-ink-faint">{label}</div>
      <div className="num mt-1 truncate text-[18px] font-semibold text-foreground">{value}</div>
    </div>
  );
}

function CreatorCard({ group }: { group: CreatorGroup }) {
  const [open, setOpen] = useState(false);
  const latest = group.events[0];
  const uniqueEventTypes = Array.from(new Set(group.events.map((event) => createdResourceType(event.event_name))));

  return (
    <article className="rounded-[8px] border border-border bg-background">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="grid w-full grid-cols-[40px_1fr_auto] items-start gap-3 p-4 text-left transition hover:bg-secondary/35 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
      >
        <span className="grid size-10 place-items-center rounded-[8px] bg-secondary text-ink-dim">
          <UserRound className="size-4" />
        </span>
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <span className="truncate text-[14px] font-semibold text-foreground">{group.principal}</span>
            <Badge variant="secondary" className="num">
              {group.events.length} created
            </Badge>
          </span>
          <span className="num mt-1 block truncate text-[10.5px] text-ink-faint">{group.principalArn ?? "principal ARN not returned"}</span>
          <span className="mt-2 block text-[11.5px] text-ink-dim">
            {uniqueEventTypes.slice(0, 4).join(", ")}
            {uniqueEventTypes.length > 4 ? ` +${uniqueEventTypes.length - 4}` : ""}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-3">
          <span className="text-right">
            <span className="block text-[10px] uppercase text-ink-faint">Latest</span>
            <span className="num block text-[11px] text-ink-dim">{formatDate(latest?.event_time)}</span>
          </span>
          <ChevronDown className={`size-4 text-ink-faint transition ${open ? "rotate-180" : ""}`} />
        </span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-border p-4">
          <div className="grid gap-2 md:grid-cols-2">
            {group.events.map((event, index) => (
              <div key={`${event.resource_id}-${event.event_name}-${event.event_time}-${index}`} className="rounded-[8px] border border-border bg-card p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[12px] font-semibold text-foreground">{createdResourceType(event.event_name)}</div>
                    <div className="num mt-1 truncate text-[11px] text-ink-dim" title={event.resource_id}>
                      {event.resource_id}
                    </div>
                  </div>
                  <Badge variant="outline" className="num text-[10px]">
                    {event.event_name}
                  </Badge>
                </div>
                <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-faint">
                  <CalendarClock className="size-3.5" />
                  <span className="num">{formatDate(event.event_time)}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-[8px] border border-border bg-[#101820] p-3 text-[#d9e7df]">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase text-[#9fb2aa]">
              <FileJson className="size-3.5" />
              Raw user creation events
            </div>
            <pre className="num max-h-72 overflow-auto text-[11px] leading-relaxed">{JSON.stringify(group.events, null, 2)}</pre>
          </div>
        </div>
      )}
    </article>
  );
}

function UserCreatorMatrix({ data }: { data: IAMGovernanceOverview }) {
  const [search, setSearch] = useState("");
  const groups = useMemo(() => groupCreators(data.resource_creators), [data.resource_creators]);
  const filteredGroups = useMemo(() => groups.filter((group) => matchesGroup(group, search)), [groups, search]);
  const iamUserNames = useMemo(() => new Set(data.users.map((user) => user.user_name)), [data.users]);
  const knownUserEventCount = data.resource_creators.filter((event) => event.principal_name && iamUserNames.has(event.principal_name)).length;

  return (
    <div>
      <div className="mb-3 grid gap-2 md:grid-cols-[1fr_auto]">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search IAM user, principal ARN, resource id, event name"
            className="h-9 w-full rounded-[8px] border border-border bg-background pl-9 pr-3 text-[12px] outline-none placeholder:text-ink-faint focus:border-[var(--ring)]"
          />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{groups.length} principals</Badge>
          <Badge variant="outline">{knownUserEventCount} IAM-user matched events</Badge>
        </div>
      </div>

      {filteredGroups.length ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {filteredGroups.map((group) => (
            <CreatorCard key={group.principalArn ?? group.principal} group={group} />
          ))}
        </div>
      ) : (
        <div className="rounded-[8px] border border-dashed border-border bg-background p-8 text-center text-[12.5px] text-ink-faint">
          No creator events match this search.
        </div>
      )}
    </div>
  );
}

export default function GovernancePage() {
  const govQuery = useIamGovernance({ refetchInterval: 30_000 });
  const data = govQuery.data;

  const stats = useMemo(() => {
    const creators = data?.resource_creators ?? [];
    const groups = groupCreators(creators);
    const eventTypes = new Set(creators.map((event) => event.event_name));
    return {
      users: data?.users.length ?? 0,
      principals: groups.length,
      events: creators.length,
      eventTypes: eventTypes.size,
    };
  }, [data]);

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage py-1">
        <div className="eyebrow">Identity & access</div>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">
              IAM & Governance
            </h1>
            <p className="mt-1.5 max-w-3xl text-[12.5px] leading-relaxed text-ink-faint">
              Real IAM users, attached policies, root posture, and CloudTrail resource-creation events grouped principal-wise.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="gap-1.5">
              <span className={`size-1.5 rounded-full ${govQuery.isFetching ? "animate-pulse bg-[var(--mint)]" : "bg-[var(--graphite)]"}`} />
              {govQuery.isFetching ? "Refreshing" : "Realtime 30s"}
            </Badge>
            <Button size="sm" variant="outline" onClick={() => void govQuery.refetch()} disabled={govQuery.isFetching}>
              <RefreshCw className={govQuery.isFetching ? "size-3.5 animate-spin" : "size-3.5"} />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      {govQuery.isError ? (
        <div className="mt-4 flex items-center gap-2 rounded-[8px] border border-red-200 bg-red-50 px-4 py-3 text-[12.5px] text-red-700">
          <AlertTriangle className="size-4" />
          Governance sync failed.
        </div>
      ) : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="IAM users" value={stats.users} />
        <Metric label="Creator principals" value={stats.principals} />
        <Metric label="Creation events" value={stats.events} />
        <Metric label="Event types" value={stats.eventTypes} />
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
                unknownLabel="Root MFA unknown"
              />
              <OverviewBadge
                ok={data.account.root_access_keys_present === null ? null : !data.account.root_access_keys_present}
                label="No root access keys"
                unknownLabel="Root access keys unknown"
              />
              <OverviewBadge
                ok={data.account.password_policy_configured}
                label="Password policy configured"
                unknownLabel="Password policy unknown"
              />
              <span className="num text-[11px] text-ink-faint">
                {data.account.alias ? `${data.account.alias} / ` : ""}
                {data.account.account_id}
              </span>
              {data.errors.account ? <span className="text-[11px] text-destructive">Account overview: {data.errors.account}</span> : null}
            </div>
          ) : null}
        </Panel>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.25fr)]">
        <Panel title="IAM users & permissions" subtitle="Every IAM user returned by AWS IAM with groups, policies, key age, and inline policy JSON." delay={180}>
          {govQuery.isLoading ? (
            <Skeleton className="h-[320px] w-full" />
          ) : data?.errors.users ? (
            <p className="text-[12.5px] text-destructive">Could not list users: {data.errors.users}</p>
          ) : (
            <GovernanceUsersTable users={data?.users ?? []} />
          )}
        </Panel>

        <Panel
          title="Who created what"
          subtitle={`CloudTrail LookupEvents, grouped IAM-user/principal-wise for trailing ${data?.resource_creators_lookback_days ?? 90} days.`}
          delay={240}
        >
          {govQuery.isLoading ? (
            <Skeleton className="h-[360px] w-full" />
          ) : data?.errors.resource_creators ? (
            <p className="text-[12.5px] text-destructive">Could not read CloudTrail: {data.errors.resource_creators}</p>
          ) : data ? (
            <UserCreatorMatrix data={data} />
          ) : null}
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Raw governance response" eyebrow="No frontend mock data" delay={320}>
          {data ? (
            <pre className="num max-h-[420px] overflow-auto rounded-[8px] border border-border bg-[#101820] p-3 text-[11px] leading-relaxed text-[#d9e7df]">
              {JSON.stringify(data, null, 2)}
            </pre>
          ) : (
            <div className="flex items-center gap-2 text-[12.5px] text-ink-faint">
              <ExternalLink className="size-4" />
              Waiting for governance API response.
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
