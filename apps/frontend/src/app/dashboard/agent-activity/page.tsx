"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Eye,
  Filter,
  Gavel,
  Loader2,
  Pause,
  Play,
  RefreshCcw,
  Search,
  ServerCog,
  Sparkles,
  TerminalSquare,
  XCircle,
} from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import type { AgentActivityEntry, AgentName } from "@/lib/cloudcare-data";
import { isApiError } from "@/lib/api";
import { useAgentActivity } from "@/lib/queries";

type AgentFilter = "All" | AgentName;
type StatusFilter = "all" | "success" | "failed";

const AGENTS: AgentName[] = ["Monitor", "Analyzer", "Decision", "Supervisor", "Executor"];

const AGENT_META: Record<AgentName, { icon: typeof Eye; label: string; tone: string }> = {
  Monitor: { icon: Eye, label: "usage capture", tone: "var(--signal)" },
  Analyzer: { icon: Brain, label: "waste scoring", tone: "var(--mint)" },
  Decision: { icon: Sparkles, label: "proposal logic", tone: "var(--ember)" },
  Supervisor: { icon: Gavel, label: "policy approval", tone: "var(--graphite)" },
  Executor: { icon: Bot, label: "safe execution", tone: "var(--destructive)" },
};

function payloadLabel(payload: Record<string, unknown>): string {
  const keys = ["run_id", "account_id", "provider", "region", "proposal_id", "resource_arn", "status"];
  const parts = keys
    .map((key) => {
      const value = payload[key];
      if (value === undefined || value === null || value === "") return null;
      return `${key}: ${String(value)}`;
    })
    .filter(Boolean);
  return parts.slice(0, 3).join(" / ") || "audit payload attached";
}

function durationLabel(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "0 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s`;
}

function timeAgo(timestamp: string): string {
  const raw = timestamp.includes("T") ? timestamp : "";
  const parsed = raw ? Date.parse(raw) : Number.NaN;
  if (!Number.isFinite(parsed)) return timestamp;
  const seconds = Math.max(0, Math.round((Date.now() - parsed) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}

function statusClass(status: AgentActivityEntry["status"]) {
  return status === "failed"
    ? "border-red-200 bg-red-50 text-red-700"
    : "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function agentMatches(entry: AgentActivityEntry, agent: AgentFilter) {
  return agent === "All" || entry.agent === agent;
}

function searchMatches(entry: AgentActivityEntry, search: string) {
  if (!search.trim()) return true;
  const haystack = `${entry.agent} ${entry.status} ${entry.message} ${JSON.stringify(entry.payload)}`.toLowerCase();
  return haystack.includes(search.trim().toLowerCase());
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="rounded-[8px] border border-border/70 bg-surface-raised/75 p-4 shadow-[0_10px_30px_rgba(16,34,46,0.05)]">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium uppercase text-ink-faint">{label}</span>
        <span className="flex size-8 items-center justify-center rounded-[8px] bg-secondary text-ink-dim">
          <Icon className="size-4" />
        </span>
      </div>
      <div className="num mt-3 text-2xl font-semibold text-foreground">{value}</div>
      <div className="mt-1 text-[11.5px] text-ink-faint">{sub}</div>
    </div>
  );
}

function AgentRail({ entries }: { entries: AgentActivityEntry[] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-5">
      {AGENTS.map((agent) => {
        const meta = AGENT_META[agent];
        const Icon = meta.icon;
        const agentEntries = entries.filter((entry) => entry.agent === agent);
        const failures = agentEntries.filter((entry) => entry.status === "failed").length;
        const latest = agentEntries[0];
        return (
          <div key={agent} className="rounded-[8px] border border-border/70 bg-background p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="flex size-8 items-center justify-center rounded-[8px]" style={{ background: `${meta.tone}1A`, color: meta.tone }}>
                <Icon className="size-4" />
              </span>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${failures ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
                {failures ? `${failures} failed` : "clean"}
              </span>
            </div>
            <div className="mt-3 text-[13px] font-semibold text-foreground">{agent}</div>
            <div className="text-[11px] text-ink-faint">{meta.label}</div>
            <div className="num mt-3 text-[11px] text-ink-dim">{latest ? `${durationLabel(latest.duration_ms)} / ${latest.timestamp}` : "no runs yet"}</div>
          </div>
        );
      })}
    </div>
  );
}

function LogRow({ entry }: { entry: AgentActivityEntry }) {
  const [open, setOpen] = useState(false);
  const meta = AGENT_META[entry.agent] ?? AGENT_META.Monitor;
  const Icon = meta.icon;
  const failed = entry.status === "failed";

  return (
    <div className="border-b border-border/60 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="grid w-full grid-cols-[36px_1fr_auto] items-start gap-3 px-3 py-3 text-left transition hover:bg-secondary/35 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
        aria-expanded={open}
      >
        <span className="relative flex size-9 items-center justify-center rounded-[8px]" style={{ background: `${failed ? "var(--destructive)" : meta.tone}1A`, color: failed ? "var(--destructive)" : meta.tone }}>
          <Icon className="size-4" />
          <span className={`absolute -right-1 -top-1 size-3 rounded-full border-2 border-background ${failed ? "bg-red-500" : "bg-emerald-500"}`} />
        </span>

        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-semibold text-foreground">{entry.agent}</span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${statusClass(entry.status)}`}>
              {entry.status}
            </span>
            <span className="num rounded-full border border-border/70 px-2 py-0.5 text-[10px] text-ink-faint">
              {durationLabel(entry.duration_ms)}
            </span>
          </span>
          <span className="mt-1 block text-[12.5px] leading-relaxed text-ink-dim">{entry.message}</span>
          <span className="mt-1 block truncate text-[11px] text-ink-faint">{payloadLabel(entry.payload)}</span>
        </span>

        <span className="flex shrink-0 items-center gap-3">
          <span className="text-right">
            <span className="num block text-[11px] text-foreground">{entry.timestamp}</span>
            <span className="num block text-[10px] text-ink-faint">{timeAgo(entry.timestamp)}</span>
          </span>
          <ChevronDown className={`size-4 text-ink-faint transition ${open ? "rotate-180" : ""}`} />
        </span>
      </button>

      {open && (
        <div className="px-3 pb-3 pl-[60px]">
          <div className="rounded-[8px] border border-border/70 bg-[#0f1720] p-3 text-[#d7e4dd]">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-[11px] font-medium uppercase text-[#9fb2aa]">
                <TerminalSquare className="size-3.5" />
                Payload
              </span>
              <span className="num text-[10px] text-[#81948d]">{entry.id}</span>
            </div>
            <pre className="num max-h-72 overflow-auto text-[11px] leading-relaxed">{JSON.stringify(entry.payload, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentActivityPage() {
  const [agentFilter, setAgentFilter] = useState<AgentFilter>("All");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [live, setLive] = useState(true);
  const activityQuery = useAgentActivity(live ? 250 : 100);

  const entries = useMemo(() => activityQuery.data ?? [], [activityQuery.data]);
  const filtered = useMemo(
    () =>
      entries.filter(
        (entry) =>
          agentMatches(entry, agentFilter) &&
          (statusFilter === "all" || entry.status === statusFilter) &&
          searchMatches(entry, search),
      ),
    [agentFilter, entries, search, statusFilter],
  );

  const failed = entries.filter((entry) => entry.status === "failed").length;
  const avgDuration =
    entries.length === 0 ? 0 : Math.round(entries.reduce((sum, entry) => sum + (Number(entry.duration_ms) || 0), 0) / entries.length);
  const lastRun = entries[0];
  const activeAgents = new Set(entries.map((entry) => entry.agent)).size;
  const errorMessage = activityQuery.error
    ? isApiError(activityQuery.error)
      ? activityQuery.error.message
      : activityQuery.error instanceof Error
        ? activityQuery.error.message
        : "Could not load activity logs."
    : null;

  return (
    <div className="mx-auto w-full max-w-[1240px] space-y-5">
      <section className="overflow-hidden rounded-[8px] border border-border/70 bg-surface-raised shadow-[0_18px_55px_rgba(16,34,46,0.08)]">
        <div className="border-b border-border/70 bg-[linear-gradient(135deg,#10222e_0%,#173a38_52%,#314033_100%)] p-5 text-white">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[11px] font-medium uppercase text-white/80">
                  <span className={`size-2 rounded-full ${activityQuery.isFetching ? "animate-pulse bg-emerald-300" : "bg-white/45"}`} />
                  {live ? "Live audit stream" : "Paused view"}
                </span>
                <span className="num rounded-full border border-white/15 bg-black/15 px-3 py-1 text-[11px] text-white/70">
                  {lastRun ? `Last run ${lastRun.timestamp}` : "Waiting for first run"}
                </span>
              </div>
              <h1 className="mt-4 text-[clamp(1.8rem,3vw,3rem)] font-semibold leading-none tracking-normal">Agent Activity Command Log</h1>
              <p className="mt-3 max-w-3xl text-[13px] leading-relaxed text-white/72">
                Real tenant audit records from Monitor, Analyzer, Decision, Supervisor, and Executor runs with payload evidence,
                durations, status, and queue-ready execution trace.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setLive((value) => !value)}
                className="inline-flex h-10 items-center gap-2 rounded-[8px] border border-white/15 bg-white/10 px-3 text-[12px] font-medium text-white transition hover:bg-white/15"
              >
                {live ? <Pause className="size-4" /> : <Play className="size-4" />}
                {live ? "Pause" : "Resume"}
              </button>
              <button
                type="button"
                onClick={() => activityQuery.refetch()}
                className="inline-flex h-10 items-center gap-2 rounded-[8px] bg-white px-3 text-[12px] font-semibold text-[#10222e] transition hover:bg-white/90"
              >
                <RefreshCcw className={`size-4 ${activityQuery.isFetching ? "animate-spin" : ""}`} />
                Refresh
              </button>
            </div>
          </div>
        </div>

        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={Activity} label="Total runs" value={String(entries.length)} sub={`${filtered.length} visible after filters`} />
          <StatCard icon={CheckCircle2} label="Healthy runs" value={String(Math.max(entries.length - failed, 0))} sub={failed ? `${failed} failures require review` : "No failed records in this window"} />
          <StatCard icon={Clock3} label="Avg duration" value={durationLabel(avgDuration)} sub="Across loaded activity records" />
          <StatCard icon={ServerCog} label="Agents active" value={`${activeAgents}/5`} sub="Pipeline components reporting logs" />
        </div>
      </section>

      {errorMessage && (
        <div className="flex items-center gap-2 rounded-[8px] border border-red-200 bg-red-50 px-4 py-3 text-[12.5px] text-red-700">
          <XCircle className="size-4" />
          {errorMessage}
        </div>
      )}

      <Panel title="Pipeline health" delay={80}>
        <AgentRail entries={entries} />
      </Panel>

      <Panel title="Realtime logs" delay={120}>
        <div className="mb-4 grid gap-3 lg:grid-cols-[1fr_auto_auto]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search logs, run ids, proposal ids, providers, messages"
              className="h-10 w-full rounded-[8px] border border-border bg-background pl-9 pr-3 text-[12.5px] text-foreground outline-none transition placeholder:text-ink-faint focus:border-[var(--ring)]"
            />
          </label>

          <div className="flex min-w-0 items-center gap-2 overflow-x-auto rounded-[8px] border border-border bg-background p-1">
            <Filter className="ml-2 size-4 shrink-0 text-ink-faint" />
            {(["All", ...AGENTS] as AgentFilter[]).map((agent) => (
              <button
                key={agent}
                type="button"
                onClick={() => setAgentFilter(agent)}
                className={`h-8 whitespace-nowrap rounded-[6px] px-3 text-[11.5px] font-medium transition ${
                  agentFilter === agent ? "bg-foreground text-background" : "text-ink-dim hover:bg-secondary"
                }`}
              >
                {agent}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 rounded-[8px] border border-border bg-background p-1">
            {(["all", "success", "failed"] as StatusFilter[]).map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`h-8 rounded-[6px] px-3 text-[11.5px] font-medium capitalize transition ${
                  statusFilter === status ? "bg-foreground text-background" : "text-ink-dim hover:bg-secondary"
                }`}
              >
                {status}
              </button>
            ))}
          </div>
        </div>

        {activityQuery.isLoading && entries.length === 0 ? (
          <div className="flex h-44 items-center justify-center rounded-[8px] border border-dashed border-border bg-background text-[12.5px] text-ink-faint">
            <Loader2 className="mr-2 size-4 animate-spin" />
            Loading real audit records
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-44 items-center justify-center rounded-[8px] border border-dashed border-border bg-background px-4 text-center text-[12.5px] text-ink-faint">
            <AlertTriangle className="mr-2 size-4" />
            No activity records match the current filters.
          </div>
        ) : (
          <div className="overflow-hidden rounded-[8px] border border-border/70 bg-background">
            {filtered.map((entry) => (
              <LogRow key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
