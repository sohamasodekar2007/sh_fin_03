"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  BrainCircuit,
  ChevronDown,
  Cpu,
  Database,
  Gauge,
  Info,
  ListChecks,
  MailCheck,
  MailX,
  Play,
  RadioTower,
  RefreshCw,
  ShieldCheck,
  StopCircle,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoneyParts } from "@/components/Money";
import { api, isApiError } from "@/lib/api";
import type { Proposal } from "@/lib/cloudcare-data";

type Provider = "aws" | "azure" | "vps";

interface AgentMetric {
  label: string;
  value: string | number;
  format?: "usd";
}

interface AgentStep {
  key: "monitor" | "analyzer" | "decision" | "supervisor" | "executor";
  name: string;
  role: string;
  status: string;
  summary: string;
  metrics: AgentMetric[];
  artifacts: string[];
}

interface CommandChartPoint {
  stage: string;
  savings: number;
}

interface CommandRun {
  run_id: string | null;
  created_at?: string;
  finished_at?: string;
  status: string;
  provider: Provider;
  account_id: string;
  region: string;
  model_router: string;
  decision_model: string;
  focus_dataset_id: string | null;
  focus_version: string;
  focus_source: string;
  focus_row_count: number;
  summary: {
    resources: number;
    findings: number;
    proposals: number;
    focus_rows: number;
    pending_approvals: number;
    blocked: number;
    potential_monthly_savings: number;
    executions_total: number;
    executed_or_simulated: number;
    blocked_or_refused: number;
  };
  steps: AgentStep[];
  chart: CommandChartPoint[];
  proposals: Proposal[];
  executions: Array<Record<string, unknown>>;
  persistence_error?: string;
  notifications?: {
    agent_command_analysis_email?: AgentCommandEmailReceipt;
  };
}

interface AgentCommandEmailReceipt {
  attempted: boolean;
  sent: boolean;
  recipient: string | null;
  reason: string | null;
  provider?: string | null;
  errors?: Array<{
    provider?: string;
    reason?: string;
    detail?: string;
  }>;
}

interface ExecutionResult {
  execution: {
    status?: string;
    execution_status?: string;
    reason_codes?: string[];
  };
  verification?: Record<string, unknown> | null;
}

interface EC2Instance {
  instance_id: string;
  name: string | null;
  state: string;
  instance_type: string | null;
  availability_zone: string | null;
  region: string;
  tags: Record<string, string>;
}

const PROVIDERS: Array<{ value: Provider; label: string }> = [
  { value: "aws", label: "AWS" },
  { value: "azure", label: "Azure" },
  { value: "vps", label: "VPS" },
];

const AUTO_SYNC_MS = 15 * 60 * 1000;

const STEP_ICONS: Record<AgentStep["key"], typeof RadioTower> = {
  monitor: RadioTower,
  analyzer: Activity,
  decision: BrainCircuit,
  supervisor: ShieldCheck,
  executor: Zap,
};

function formatCountdown(ms: number) {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

const STEP_COLORS: Record<AgentStep["key"], string> = {
  monitor: "var(--signal)",
  analyzer: "var(--mint)",
  decision: "var(--violet)",
  supervisor: "var(--amber)",
  executor: "var(--foreground)",
};

function formatMetric(metric: AgentMetric) {
  if (metric.format === "usd" && typeof metric.value === "number") {
    return formatMoneyParts(metric.value).usd;
  }
  return String(metric.value);
}

function shortTimestamp(value: string | undefined) {
  if (!value) return "Waiting";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Live";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function emailStatusText(email: AgentCommandEmailReceipt | undefined) {
  if (!email) return "Waiting for next run";
  if (email.sent) return `Sent to ${email.recipient ?? "configured recipient"}${email.provider ? ` via ${email.provider}` : ""}`;
  if (email.reason?.includes("BREVO_UNAUTHORIZED_IP") || email.reason?.includes("SMTP_UNAUTHORIZED_IP")) {
    return "Not sent - authorize IP 115.112.9.139 in Brevo Security > Authorized IPs";
  }
  if (email.reason === "NO_RECIPIENT_EMAIL") return "Not sent - no recipient email is configured";
  return `Not sent${email.reason ? ` - ${email.reason}` : ""}`;
}

function KpiBox({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Cpu }) {
  return (
    <div className="hairline-top rounded-md bg-card p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-faint">{label}</span>
        <Icon className="size-4 shrink-0 text-ink-faint" />
      </div>
      <div className="num mt-4 text-[1.85rem] font-semibold leading-none text-foreground">{value}</div>
    </div>
  );
}

function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[360px] overflow-auto rounded-md border border-border bg-background p-3 text-[11px] leading-relaxed text-ink-dim">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function DetailRows({ rows }: { rows: Array<[string, unknown]> }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="rounded-md border border-border bg-background px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-[0.1em] text-ink-faint">{label}</div>
          <div className="num mt-1 break-words text-[12px] font-medium text-foreground">{valueText(value)}</div>
        </div>
      ))}
    </div>
  );
}

function agentDetailRows(step: AgentStep, data: CommandRun | undefined): Array<[string, unknown]> {
  const summary = data?.summary;
  const base: Array<[string, unknown]> = [
    ["Agent key", step.key],
    ["Status", step.status],
    ["Run id", data?.run_id],
    ["Provider", data?.provider],
    ["Account", data?.account_id],
    ["Region", data?.region],
  ];

  if (step.key === "monitor") {
    return [
      ...base,
      ["Focus dataset", data?.focus_dataset_id],
      ["Focus version", data?.focus_version],
      ["Focus source", data?.focus_source],
      ["Focus rows", data?.focus_row_count],
      ["Resources", summary?.resources],
    ];
  }
  if (step.key === "analyzer") {
    return [...base, ["Findings", summary?.findings], ["Resources analyzed", summary?.resources]];
  }
  if (step.key === "decision") {
    return [
      ...base,
      ["Model router", data?.model_router],
      ["Decision model", data?.decision_model],
      ["Proposals", summary?.proposals],
      ["Potential monthly savings", formatMoneyParts(summary?.potential_monthly_savings ?? 0).usd],
    ];
  }
  if (step.key === "supervisor") {
    return [
      ...base,
      ["Pending approvals", summary?.pending_approvals],
      ["Blocked", summary?.blocked],
      ["Total proposals", summary?.proposals],
    ];
  }
  return [
    ...base,
    ["Executions total", summary?.executions_total],
    ["Executed or simulated", summary?.executed_or_simulated],
    ["Blocked or refused", summary?.blocked_or_refused],
  ];
}

function AgentCard({
  step,
  index,
  expanded,
  onToggle,
  data,
}: {
  step: AgentStep;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  data: CommandRun | undefined;
}) {
  const Icon = STEP_ICONS[step.key];
  return (
    <article className="hairline-top flex min-h-[292px] flex-col rounded-md bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid size-11 shrink-0 place-items-center rounded-md border border-border bg-background">
            <Icon className="size-5" style={{ color: STEP_COLORS[step.key] }} />
          </div>
          <div className="min-w-0">
            <div className="num text-[10px] text-ink-faint">0{index + 1}</div>
            <h3 className="text-[15px] font-semibold leading-tight text-foreground">{step.name}</h3>
            <p className="mt-0.5 text-[11px] leading-snug text-ink-faint">{step.role}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant={step.status === "success" || step.status === "ready" ? "secondary" : "outline"}>
            {step.status}
          </Badge>
          <Button type="button" variant="outline" size="icon" className="size-8" onClick={onToggle} aria-label={`${expanded ? "Collapse" : "Expand"} ${step.name}`}>
            <ChevronDown className={`size-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </Button>
        </div>
      </div>

      <p className="mt-4 min-h-[44px] text-[12.5px] leading-relaxed text-ink-dim">{step.summary}</p>

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {step.metrics.map((metric) => (
          <div key={metric.label} className="rounded-md border border-border bg-background px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-[0.1em] text-ink-faint">{metric.label}</div>
            <div className="num mt-1 break-words text-[13px] font-semibold text-foreground">{formatMetric(metric)}</div>
          </div>
        ))}
      </div>

      {expanded && (
        <div className="mt-4 space-y-4 border-t border-border pt-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              <Info className="size-3.5" />
              Runtime details
            </div>
            <DetailRows rows={agentDetailRows(step, data)} />
          </div>

          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              <ListChecks className="size-3.5" />
              All metrics
            </div>
            <JsonBlock value={step.metrics} />
          </div>
        </div>
      )}

      <div className="mt-auto pt-4">
        <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
          <Database className="size-3.5" />
          MongoDB
        </div>
        <div className="flex flex-wrap gap-1.5">
          {step.artifacts.map((artifact) => (
            <span key={artifact} className="rounded border border-border bg-background px-2 py-1 text-[10.5px] text-ink-dim">
              {artifact}
            </span>
          ))}
        </div>
      </div>
    </article>
  );
}

export default function AgentCommandPage() {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<Provider>("aws");
  const [expandedSteps, setExpandedSteps] = useState<Record<AgentStep["key"], boolean>>({
    monitor: true,
    analyzer: true,
    decision: true,
    supervisor: true,
    executor: true,
  });
  const [showPayload, setShowPayload] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const [nextSyncAt, setNextSyncAt] = useState(() => Date.now() + AUTO_SYNC_MS);

  const latestQuery = useQuery({
    queryKey: ["agent-command-latest"],
    queryFn: () => api.get<CommandRun>("/v1/agent-command/latest"),
    refetchInterval: AUTO_SYNC_MS,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
  });

  const instancesQuery = useQuery({
    queryKey: ["agent-command-ec2-instances"],
    queryFn: () => api.get<EC2Instance[]>("/v1/agent-command/ec2-instances"),
    refetchInterval: AUTO_SYNC_MS,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
  });

  const runMutation = useMutation({
    mutationFn: () => api.post<CommandRun>(`/v1/agent-command/run?provider=${provider}`),
    onSuccess: (data) => {
      setNextSyncAt(Date.now() + AUTO_SYNC_MS);
      queryClient.setQueryData(["agent-command-latest"], data);
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
      const email = data.notifications?.agent_command_analysis_email;
      if (email?.sent) {
        toast.success(`Analysis email sent to ${email.recipient ?? "configured recipient"}.`);
      } else if (email?.attempted) {
        toast.error(emailStatusText(email));
      } else {
        toast.warning(emailStatusText(email));
      }
    },
  });

  const stopInstanceMutation = useMutation({
    mutationFn: (instanceId: string) =>
      api.post<ExecutionResult>(`/v1/agent-command/ec2-instances/${instanceId}/stop`, { confirm: true }),
    onSuccess: (result) => {
      setNextSyncAt(Date.now() + AUTO_SYNC_MS);
      const status = result.execution.status;
      if (status === "executed" || status === "no_op") {
        toast.success(status === "no_op" ? "Instance already stopped." : "Instance stopped.");
      } else {
        toast.error(result.execution.reason_codes?.join(", ") || `Stop ${status ?? "did not complete"}.`);
      }
      queryClient.invalidateQueries({ queryKey: ["agent-command-ec2-instances"] });
      queryClient.invalidateQueries({ queryKey: ["agent-command-latest"] });
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
    },
    onError: (err) => {
      toast.error(isApiError(err) ? err.message : "Could not stop this EC2 instance.");
    },
  });

  const data = latestQuery.data ?? runMutation.data;
  const steps = data?.steps ?? [];
  const proposals = useMemo(() => data?.proposals ?? [], [data?.proposals]);
  const chart = data?.chart?.length ? data.chart : [{ stage: "Ready", savings: 0 }];
  const pending = proposals.filter((proposal) => proposal.status === "pending_approval");
  const loading = latestQuery.isLoading && !runMutation.data;
  const running = runMutation.isPending;
  const syncing = (latestQuery.isFetching || instancesQuery.isFetching) && !loading && !running;
  const instances = instancesQuery.data ?? [];
  const allExpanded = steps.length > 0 && steps.every((step) => expandedSteps[step.key]);
  const analysisEmail = data?.notifications?.agent_command_analysis_email;
  const countdown = formatCountdown(nextSyncAt - now);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (now < nextSyncAt || running || syncing) return;
    setNextSyncAt(Date.now() + AUTO_SYNC_MS);
    void latestQuery.refetch();
    void instancesQuery.refetch();
    void queryClient.invalidateQueries({ queryKey: ["resources"] });
    void queryClient.invalidateQueries({ queryKey: ["proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
  }, [instancesQuery, latestQuery, nextSyncAt, now, queryClient, running, syncing]);

  function setEveryStep(open: boolean) {
    setExpandedSteps({
      monitor: open,
      analyzer: open,
      decision: open,
      supervisor: open,
      executor: open,
    });
  }

  function refreshAll() {
    setNextSyncAt(Date.now() + AUTO_SYNC_MS);
    void latestQuery.refetch();
    void instancesQuery.refetch();
    void queryClient.invalidateQueries({ queryKey: ["resources"] });
    void queryClient.invalidateQueries({ queryKey: ["proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
  }

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage rounded-md border border-border bg-card p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0">
            <div className="eyebrow">Hackathon architecture</div>
            <h1 className="mt-1 text-[clamp(1.65rem,2.9vw,2.55rem)] font-bold leading-[1.02] text-foreground">
              Five-agent command center
            </h1>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge variant="secondary">{data?.decision_model ?? "gpt-5.6-sol"}</Badge>
              <Badge variant="outline">{data?.model_router ?? "api.kineticrouter.com"}</Badge>
              <Badge variant={data?.focus_source === "live" ? "secondary" : "outline"}>
                FOCUS {data?.focus_version ?? "1.2"}
              </Badge>
              <Badge variant="outline">{data?.focus_source ?? "waiting"}</Badge>
              <Badge variant="outline">{data?.run_id ? `Run ${data.run_id.slice(0, 8)}` : "No run yet"}</Badge>
              {analysisEmail ? (
                <Badge variant={analysisEmail.sent ? "secondary" : "destructive"}>
                  {analysisEmail.sent ? <MailCheck className="size-3" /> : <MailX className="size-3" />}
                  {analysisEmail.sent ? "Email sent" : "Email not sent"}
                </Badge>
              ) : null}
              <Badge variant="outline">Auto sync 15m</Badge>
              <Badge variant="outline" className="num">Next {countdown}</Badge>
              {syncing ? (
                <Badge variant="secondary">
                  <RefreshCw className="size-3 animate-spin" />
                  Syncing
                </Badge>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="flex rounded-md border border-border bg-background p-1">
              {PROVIDERS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setProvider(item.value)}
                  className="rounded px-3 py-1.5 text-[12px] font-medium transition-colors"
                  style={{
                    background: provider === item.value ? "var(--accent)" : "transparent",
                    color: provider === item.value ? "var(--foreground)" : "var(--ink-dim)",
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <Button onClick={() => runMutation.mutate()} disabled={running}>
              {running ? <Gauge className="size-4 animate-spin" /> : <Play className="size-4" />}
              {running ? "Running" : "Run pipeline"}
            </Button>
            <Button
              variant="outline"
              onClick={refreshAll}
              disabled={syncing || running}
            >
              <RefreshCw className={syncing ? "size-4 animate-spin" : "size-4"} />
              {syncing ? "Refreshing" : "Refresh"}
            </Button>
            <Button variant="outline" onClick={() => setEveryStep(!allExpanded)} disabled={!steps.length}>
              <ChevronDown className={`size-4 transition-transform ${allExpanded ? "rotate-180" : ""}`} />
              {allExpanded ? "Collapse agents" : "Expand agents"}
            </Button>
          </div>
        </div>

        <div className="mt-5 grid gap-2 text-[12px] sm:grid-cols-3">
          <div className="rounded-md border border-border bg-background px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Account</div>
            <div className="num mt-1 truncate font-medium text-foreground">{data?.account_id ?? "demo-account"}</div>
          </div>
          <div className="rounded-md border border-border bg-background px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Region</div>
            <div className="num mt-1 truncate font-medium text-foreground">{data?.region ?? "ap-south-1"}</div>
          </div>
          <div className="rounded-md border border-border bg-background px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Last run</div>
            <div className="num mt-1 truncate font-medium text-foreground">{running ? "Running now" : shortTimestamp(data?.finished_at)}</div>
          </div>
          <div className="rounded-md border border-border bg-background px-3 py-2.5 sm:col-span-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Cost feed</div>
            <div className="num mt-1 truncate font-medium text-foreground">
              {data?.focus_row_count ?? 0} FOCUS rows from {data?.focus_source ?? "waiting"}
              {data?.focus_dataset_id ? ` - ${data.focus_dataset_id.slice(0, 8)}` : ""}
            </div>
          </div>
          <div className="rounded-md border border-border bg-background px-3 py-2.5 sm:col-span-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Analysis email</div>
            <div className="num mt-1 truncate font-medium text-foreground">
              {emailStatusText(analysisEmail)}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {loading ? (
          <>
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </>
        ) : (
          <>
            <KpiBox label="Resources" value={String(data?.summary.resources ?? 0)} icon={Cpu} />
            <KpiBox label="Findings" value={String(data?.summary.findings ?? 0)} icon={Activity} />
            <KpiBox label="Potential/mo" value={formatMoneyParts(data?.summary.potential_monthly_savings ?? 0).usd} icon={BrainCircuit} />
            <KpiBox label="Awaiting approval" value={String(data?.summary.pending_approvals ?? pending.length)} icon={ShieldCheck} />
          </>
        )}
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-2 2xl:grid-cols-3">
        {loading
          ? Array.from({ length: 5 }, (_, index) => <Skeleton key={index} className="h-[260px] w-full" />)
          : steps.map((step, index) => (
              <AgentCard
                key={step.key}
                step={step}
                index={index}
                expanded={expandedSteps[step.key]}
                onToggle={() => setExpandedSteps((current) => ({ ...current, [step.key]: !current[step.key] }))}
                data={data}
              />
            ))}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.45fr)]">
        <Panel title="Savings runway" eyebrow="Impact" subtitle="Detected, routed, approved, and blocked savings for the active run." delay={160}>
          <div className="h-[330px]">
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chart} margin={{ left: 4, right: 12, top: 14, bottom: 4 }}>
                <defs>
                  <linearGradient id="agentCommandSavings" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--mint)" stopOpacity={0.48} />
                    <stop offset="100%" stopColor="var(--mint)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="stage" tickLine={false} axisLine={false} tick={{ fill: "var(--ink-faint)", fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fill: "var(--ink-faint)", fontSize: 11 }} width={64} />
                <Tooltip formatter={(value) => formatMoneyParts(Number(value)).usd} contentStyle={{ borderRadius: 8, borderColor: "var(--border)" }} />
                <Area type="monotone" dataKey="savings" stroke="var(--mint)" strokeWidth={2} fill="url(#agentCommandSavings)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Live Control" eyebrow="Human approval" subtitle="Selectively stop running EC2 instances through the Executor path." delay={200}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <Badge variant="outline">{instances.length} instances</Badge>
            <Button
              size="sm"
              variant="outline"
              disabled={instancesQuery.isFetching}
              onClick={() => instancesQuery.refetch()}
            >
              <RefreshCw className={instancesQuery.isFetching ? "size-3.5 animate-spin" : "size-3.5"} />
              Refresh EC2
            </Button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-[12px]">
              <thead className="border-b border-border text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                <tr>
                  <th className="pb-3 pr-3 font-medium">Instance</th>
                  <th className="pb-3 pr-3 font-medium">State</th>
                  <th className="pb-3 pr-3 font-medium">Type</th>
                  <th className="pb-3 pr-3 font-medium">AZ</th>
                  <th className="pb-3 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {instances.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-10 text-center text-ink-faint">
                      No EC2 instances returned by AWS.
                    </td>
                  </tr>
                ) : (
                  instances.map((instance) => {
                    const stopping =
                      stopInstanceMutation.isPending && stopInstanceMutation.variables === instance.instance_id;
                    const canStop = instance.state === "running";
                    return (
                      <tr key={instance.instance_id} className="border-b border-border/70 last:border-0">
                        <td className="py-3 pr-3">
                          <div className="font-medium text-foreground">{instance.name ?? instance.instance_id}</div>
                          <div className="num mt-0.5 text-[10.5px] text-ink-faint">{instance.instance_id}</div>
                        </td>
                        <td className="py-3 pr-3">
                          <Badge variant={canStop ? "secondary" : "outline"}>{instance.state}</Badge>
                        </td>
                        <td className="num py-3 pr-3 text-ink-dim">{instance.instance_type ?? "-"}</td>
                        <td className="num py-3 pr-3 text-ink-dim">{instance.availability_zone ?? "-"}</td>
                        <td className="py-3 text-right">
                          <Button
                            size="sm"
                            variant={canStop ? "destructive" : "outline"}
                            disabled={!canStop || stopping}
                            onClick={() => {
                              if (window.confirm(`Stop ${instance.name ?? instance.instance_id}?`)) {
                                stopInstanceMutation.mutate(instance.instance_id);
                              }
                            }}
                          >
                            {stopping ? <Gauge className="size-3.5 animate-spin" /> : <StopCircle className="size-3.5" />}
                            {stopping ? "Stopping" : canStop ? "Stop" : "Stopped"}
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Execution ledger" eyebrow="Executor" subtitle="Recent simulation/live execution records attached to this run." delay={280}>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chart} margin={{ left: 0, right: 8, top: 10, bottom: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="stage" tickLine={false} axisLine={false} tick={{ fill: "var(--ink-faint)", fontSize: 11 }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fill: "var(--ink-faint)", fontSize: 11 }} width={64} />
              <Tooltip formatter={(value) => formatMoneyParts(Number(value)).usd} contentStyle={{ borderRadius: 8, borderColor: "var(--border)" }} />
              <Bar dataKey="savings" radius={[4, 4, 0, 0]}>
                {chart.map((entry) => (
                  <Cell key={entry.stage} fill={entry.stage === "Blocked" ? "var(--graphite)" : "var(--signal)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Run payload explorer" eyebrow="Full response" subtitle="Complete data returned by /v1/agent-command/latest for this dashboard." delay={320}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <Badge variant="outline">{data?.status ?? "waiting"}</Badge>
            <Button type="button" variant="outline" size="sm" onClick={() => setShowPayload((value) => !value)}>
              <ChevronDown className={`size-3.5 transition-transform ${showPayload ? "rotate-180" : ""}`} />
              {showPayload ? "Hide payload" : "Show payload"}
            </Button>
          </div>
          {data?.persistence_error && (
            <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
              {data.persistence_error}
            </div>
          )}
          {showPayload ? <JsonBlock value={data ?? { status: "waiting" }} /> : null}
        </Panel>
      </div>
    </div>
  );
}
