"use client";

import { useMemo, useState } from "react";
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
  CheckCircle2,
  Cpu,
  Database,
  Gauge,
  Play,
  RadioTower,
  RefreshCw,
  RotateCw,
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
import { fmtPctOr } from "@/lib/format";
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
}

interface ExecutionResult {
  execution: {
    status?: string;
    execution_status?: string;
    reason_codes?: string[];
  };
  verification?: Record<string, unknown> | null;
}

interface ApprovalResult {
  status: string;
  proposal_id: string;
  execution?: {
    execution_status?: string;
    reason_codes?: string[];
  };
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

const STEP_ICONS: Record<AgentStep["key"], typeof RadioTower> = {
  monitor: RadioTower,
  analyzer: Activity,
  decision: BrainCircuit,
  supervisor: ShieldCheck,
  executor: Zap,
};

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

function riskTone(score: number | undefined) {
  if (score === undefined || Number.isNaN(score)) return "secondary";
  if (score < 0.35) return "secondary";
  if (score < 0.65) return "outline";
  return "destructive";
}

function actionLabel(actionType: string) {
  return actionType.replace(/_/g, " ");
}

function resourceLabel(resourceArn: string) {
  const slash = resourceArn.lastIndexOf("/");
  return slash >= 0 ? resourceArn.slice(slash + 1) : resourceArn;
}

function shortTimestamp(value: string | undefined) {
  if (!value) return "Waiting";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Live";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function executorState(proposal: Proposal) {
  const executionStatus = proposal.execution_status;
  const reasons = proposal.execution_reason_codes?.join(", ");

  if (proposal.status === "pending_approval") {
    return { label: "Awaiting approval", detail: "Human approval required", action: "approve" as const };
  }
  if (proposal.status === "approved") {
    if (executionStatus === "refused" || executionStatus === "failed") {
      return { label: "Retry", detail: reasons || executionStatus, action: "execute" as const };
    }
    return { label: "Execute", detail: "Approved, executor not completed", action: "execute" as const };
  }
  if (proposal.status === "executed" || proposal.status === "verified") {
    const mode = proposal.execution_mode ? ` (${proposal.execution_mode})` : "";
    return { label: "Done", detail: `${proposal.execution_status ?? proposal.status}${mode}`, action: "none" as const };
  }
  if (proposal.status === "blocked") {
    return { label: "Blocked", detail: reasons || "Policy blocked", action: "none" as const };
  }
  if (proposal.status === "rejected") {
    return { label: "Rejected", detail: proposal.rejection_reason || "Rejected", action: "none" as const };
  }
  return { label: "Locked", detail: proposal.status, action: "none" as const };
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

function AgentCard({ step, index }: { step: AgentStep; index: number }) {
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
        <Badge variant={step.status === "success" || step.status === "ready" ? "secondary" : "outline"} className="shrink-0">
          {step.status}
        </Badge>
      </div>

      <p className="mt-4 min-h-[44px] text-[12.5px] leading-relaxed text-ink-dim">{step.summary}</p>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {step.metrics.slice(0, 3).map((metric) => (
          <div key={metric.label} className="rounded-md border border-border bg-background px-3 py-2.5">
            <div className="truncate text-[10px] uppercase tracking-[0.1em] text-ink-faint">{metric.label}</div>
            <div className="num mt-1 truncate text-[13px] font-semibold text-foreground">{formatMetric(metric)}</div>
          </div>
        ))}
      </div>

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

  const latestQuery = useQuery({
    queryKey: ["agent-command-latest"],
    queryFn: () => api.get<CommandRun>("/v1/agent-command/latest"),
    refetchInterval: 10_000,
  });

  const instancesQuery = useQuery({
    queryKey: ["agent-command-ec2-instances"],
    queryFn: () => api.get<EC2Instance[]>("/v1/agent-command/ec2-instances"),
    refetchInterval: 10_000,
  });

  const runMutation = useMutation({
    mutationFn: () => api.post<CommandRun>(`/v1/agent-command/run?provider=${provider}`),
    onSuccess: (data) => {
      queryClient.setQueryData(["agent-command-latest"], data);
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
    },
  });

  const executeMutation = useMutation({
    mutationFn: (proposalId: string) => api.post<ExecutionResult>(`/v1/execute/${proposalId}`),
    onSuccess: (result) => {
      const status = result?.execution?.status;
      const reasons = result?.execution?.reason_codes?.join(", ");
      if (status === "executed" || status === "no_op") {
        toast.success("Executor completed.");
      } else {
        toast.error(reasons || `Executor ${status ?? "did not complete"}.`);
      }
      queryClient.invalidateQueries({ queryKey: ["agent-command-latest"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
    },
    onError: (err) => {
      toast.error(isApiError(err) ? err.message : "Could not execute this proposal.");
    },
  });

  const approveMutation = useMutation({
    mutationFn: (proposalId: string) => api.post<ApprovalResult>(`/v1/approvals/${proposalId}/approve`),
    onSuccess: (result) => {
      const execution = result?.execution;
      if (!execution || execution.execution_status === "executed" || execution.execution_status === "no_op") {
        toast.success("Proposal approved and sent to executor.");
      } else {
        toast.error(execution.reason_codes?.join(", ") || `Executor ${execution.execution_status ?? "did not complete"}.`);
      }
      queryClient.invalidateQueries({ queryKey: ["agent-command-latest"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
    },
    onError: (err) => {
      toast.error(isApiError(err) ? err.message : "Could not approve this proposal.");
    },
  });

  const stopInstanceMutation = useMutation({
    mutationFn: (instanceId: string) =>
      api.post<ExecutionResult>(`/v1/agent-command/ec2-instances/${instanceId}/stop`, { confirm: true }),
    onSuccess: (result) => {
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
  const possible = proposals.filter((proposal) => proposal.status !== "rejected").slice(0, 8);
  const loading = latestQuery.isLoading && !runMutation.data;
  const running = runMutation.isPending;
  const refreshing = latestQuery.isFetching && !loading && !running;
  const instances = instancesQuery.data ?? [];

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
              <Badge variant="outline">Refresh 10s</Badge>
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
              onClick={() => {
                latestQuery.refetch();
                queryClient.invalidateQueries({ queryKey: ["resources"] });
                queryClient.invalidateQueries({ queryKey: ["proposals"] });
                queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
              }}
              disabled={refreshing || running}
            >
              <RefreshCw className={refreshing ? "size-4 animate-spin" : "size-4"} />
              {refreshing ? "Refreshing" : "Refresh"}
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

      <div className="mt-4 grid gap-3 lg:grid-cols-2 2xl:grid-cols-5">
        {loading
          ? Array.from({ length: 5 }, (_, index) => <Skeleton key={index} className="h-[260px] w-full" />)
          : steps.map((step, index) => <AgentCard key={step.key} step={step} index={index} />)}
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

        <Panel title="Live EC2 control" eyebrow="Human approval" subtitle="Selectively stop running EC2 instances through the Executor path." delay={200}>
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

        <Panel title="Supervisor queue" eyebrow="HITL" subtitle="Approval moves a proposal into the guarded Executor workflow." delay={220}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-[12px]">
              <thead className="border-b border-border text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                <tr>
                  <th className="pb-3 pr-3 font-medium">Resource</th>
                  <th className="pb-3 pr-3 font-medium">Action</th>
                  <th className="pb-3 pr-3 font-medium">Savings</th>
                  <th className="pb-3 pr-3 font-medium">Risk</th>
                  <th className="pb-3 pr-3 font-medium">Status</th>
                  <th className="pb-3 text-right font-medium">Executor</th>
                </tr>
              </thead>
              <tbody>
                {possible.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-ink-faint">
                      Run the pipeline to populate the supervisor queue.
                    </td>
                  </tr>
                ) : (
                  possible.map((proposal) => {
                    const riskScore = typeof proposal.risk_score === "number" ? proposal.risk_score : undefined;
                    const executor = executorState(proposal);
                    const approving = approveMutation.isPending && approveMutation.variables === proposal.proposal_id;
                    const executing = executeMutation.isPending && executeMutation.variables === proposal.proposal_id;
                    const busy = approving || executing;
                    return (
                      <tr key={proposal.proposal_id} className="border-b border-border/70 last:border-0">
                        <td className="py-3 pr-3">
                          <div className="font-medium text-foreground">{resourceLabel(proposal.resource_arn)}</div>
                          <div className="num mt-0.5 text-[10.5px] text-ink-faint">{proposal.environment}</div>
                        </td>
                        <td className="py-3 pr-3 capitalize text-ink-dim">{actionLabel(proposal.action_type)}</td>
                        <td className="num py-3 pr-3 font-semibold text-foreground">
                          {formatMoneyParts(Number(proposal.expected_monthly_savings) || 0).usd}
                        </td>
                        <td className="py-3 pr-3">
                          <Badge variant={riskTone(riskScore)}>
                            {riskScore === undefined ? proposal.risk_level : fmtPctOr(riskScore, 0)}
                          </Badge>
                        </td>
                        <td className="py-3 pr-3">
                          <Badge variant={proposal.status === "pending_approval" || proposal.status === "approved" ? "secondary" : "outline"}>{proposal.status}</Badge>
                          <div className="mt-1 max-w-[220px] truncate text-[10.5px] text-ink-faint" title={executor.detail}>
                            {executor.detail}
                          </div>
                        </td>
                        <td className="py-3 text-right">
                          <Button
                            size="sm"
                            variant={executor.action === "none" ? "outline" : "default"}
                            disabled={executor.action === "none" || busy}
                            onClick={() => {
                              if (executor.action === "approve") approveMutation.mutate(proposal.proposal_id);
                              if (executor.action === "execute") executeMutation.mutate(proposal.proposal_id);
                            }}
                          >
                            {busy ? (
                              <Gauge className="size-3.5 animate-spin" />
                            ) : executor.action === "approve" ? (
                              <CheckCircle2 className="size-3.5" />
                            ) : executor.action === "execute" ? (
                              <RotateCw className="size-3.5" />
                            ) : (
                              <ShieldCheck className="size-3.5" />
                            )}
                            {busy ? "Working" : executor.label}
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
    </div>
  );
}
