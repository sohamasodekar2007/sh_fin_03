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
  Bell,
  BrainCircuit,
  Bot,
  ChevronDown,
  Cloud,
  Cpu,
  FileSearch,
  Gauge,
  KeyRound,
  MailCheck,
  MailX,
  Network,
  Play,
  RadioTower,
  RefreshCw,
  Server,
  Settings2,
  ShieldCheck,
  StopCircle,
  Workflow,
  Tags,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { Panel } from "@/components/cfo/Panel";
import { ResourceDetailSheet } from "@/components/cfo/ResourceDetailSheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoneyParts } from "@/components/Money";
import { api, isApiError } from "@/lib/api";
import type {
  AgentActivityEntry,
  AwsCoreServicesExternalFactor,
  Proposal,
  ResourceItem,
} from "@/lib/cloudcare-data";
import { useAgentActivity, useIamGovernance, useProposals, useResources } from "@/lib/queries";

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

type Ec2PowerAction = "start" | "stop";

interface EC2Instance {
  instance_id: string;
  name: string | null;
  state: string;
  instance_type: string | null;
  availability_zone: string | null;
  region: string;
  tags: Record<string, string>;
}

interface SqsStatus {
  enabled: boolean;
  queue_url_configured: boolean;
  running: boolean;
  processed_total: number;
  last_error: string | null;
  last_poll_at: string | null;
  region: string;
}

type CommandStatus = "live" | "ready" | "needs_attention" | "waiting";

interface ServiceAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "default" | "outline" | "destructive";
  icon?: typeof Cpu;
}

interface ServiceCommand {
  key: string;
  title: string;
  group: string;
  status: CommandStatus;
  icon: typeof Cpu;
  headline: string;
  metrics: Array<[string, string | number]>;
  evidence: string[];
  actions: ServiceAction[];
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
  supervisor: "var(--ember)",
  executor: "var(--foreground)",
};

const STEP_LABELS: Record<AgentStep["key"], string> = {
  monitor: "Research input",
  analyzer: "Findings",
  decision: "Decisions",
  supervisor: "Approval routing",
  executor: "Execution ledger",
};

const STATUS_COPY: Record<CommandStatus, { label: string; tone: string }> = {
  live: { label: "Live", tone: "var(--mint)" },
  ready: { label: "Ready", tone: "var(--signal)" },
  needs_attention: { label: "Needs attention", tone: "var(--destructive)" },
  waiting: { label: "Waiting", tone: "var(--ink-faint)" },
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

function proposalSavings(proposal: Proposal) {
  return Number(proposal.expected_monthly_savings) || 0;
}

function projectedProposalSavings(proposals: Proposal[]) {
  return proposals
    .filter((proposal) => proposal.status === "approved" || proposal.status === "pending_approval")
    .reduce((sum, proposal) => sum + proposalSavings(proposal), 0);
}

function serviceLabelForResource(resource: ResourceItem) {
  const type = resource.resource_type ?? resource.type ?? "unknown";
  const normalized = type.toLowerCase();
  if (normalized.includes("ec2")) return "Amazon EC2";
  if (normalized.includes("ebs")) return "Amazon EBS";
  if (normalized.includes("rds")) return "Amazon RDS";
  if (normalized.includes("dynamodb")) return "Amazon DynamoDB";
  if (normalized.includes("lambda")) return "AWS Lambda";
  if (normalized.includes("security_group")) return "Security Group";
  if (normalized.includes("vpc")) return "Amazon VPC";
  if (normalized.includes("s3")) return "Amazon S3";
  return type.replace(/_/g, " ");
}

const EC2_INSTANCE_SPECS: Record<string, { vcpu: number; memory_gib: number }> = {
  "t3.micro": { vcpu: 2, memory_gib: 1 },
};

function isEc2Resource(resource: ResourceItem) {
  return resource.resource_type === "ec2_instance" || resource.id.startsWith("i-");
}

function hardwareForResource(resource: ResourceItem) {
  if (!isEc2Resource(resource)) return { instanceType: null, ram: null, vcpu: null };
  const instanceType = resource.instance_type ?? resource.type ?? null;
  const fallback = instanceType ? EC2_INSTANCE_SPECS[instanceType] : undefined;
  return {
    instanceType,
    ram: resource.memory_gib ?? fallback?.memory_gib ?? null,
    vcpu: resource.vcpu ?? fallback?.vcpu ?? null,
  };
}

function compactTags(tags: Record<string, string>) {
  const entries = Object.entries(tags);
  if (!entries.length) return "untagged";
  return entries.slice(0, 4).map(([key, value]) => `${key}=${value}`).join(", ");
}

function resourceCostText(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "not costed";
  return formatMoneyParts(value).usd;
}

function proposalInstanceId(proposal: Proposal) {
  const fromParams = proposal.parameters.instance_id;
  if (typeof fromParams === "string" && fromParams) return fromParams;
  if (proposal.resource_id) return proposal.resource_id;
  const idx = proposal.resource_arn.lastIndexOf("/");
  return idx >= 0 ? proposal.resource_arn.slice(idx + 1) : proposal.resource_arn;
}

function proposalResourceName(proposal: Proposal) {
  return proposal.resource_name || proposalInstanceId(proposal);
}

function proposalTags(proposal: Proposal) {
  return proposal.tags ?? {};
}

function tagValue(tags: Record<string, string>, key: string) {
  const match = Object.entries(tags).find(([candidate]) => candidate.toLowerCase() === key.toLowerCase());
  return match?.[1] || "untagged";
}

function isInstanceProposal(proposal: Proposal) {
  if (proposal.resource_type === "ec2_instance") return true;
  if (typeof proposal.parameters.instance_id === "string") return true;
  return proposal.resource_arn.includes(":instance/");
}

const RISK_WEIGHT: Record<string, number> = { low: 1, medium: 2, high: 3, critical: 4 };

function higherRisk(current: Proposal["risk_level"], next: Proposal["risk_level"]) {
  return RISK_WEIGHT[next] > RISK_WEIGHT[current] ? next : current;
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[360px] overflow-auto rounded-md border border-border bg-background p-3 text-[11px] leading-relaxed text-ink-dim">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function latestActivity(entries: AgentActivityEntry[], agent: AgentStep["name"]) {
  return entries.find((entry) => entry.agent === agent);
}

function serviceStatus(ok: boolean, loading: boolean, error: boolean): CommandStatus {
  if (loading) return "waiting";
  if (error) return "needs_attention";
  return ok ? "live" : "ready";
}

function ServiceCommandCard({ service }: { service: ServiceCommand }) {
  const Icon = service.icon;
  const status = STATUS_COPY[service.status];
  return (
    <article className="hairline-top flex min-h-[310px] flex-col rounded-md bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid size-11 shrink-0 place-items-center rounded-md border border-border bg-background">
            <Icon className="size-5" style={{ color: status.tone }} />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">{service.group}</div>
            <h3 className="mt-0.5 text-[15px] font-semibold leading-tight text-foreground">{service.title}</h3>
          </div>
        </div>
        <Badge variant={service.status === "needs_attention" ? "destructive" : service.status === "live" ? "secondary" : "outline"}>
          <span className="inline-block size-1.5 rounded-full" style={{ background: status.tone }} />
          {status.label}
        </Badge>
      </div>

      <p className="mt-4 min-h-[44px] text-[12.5px] leading-relaxed text-ink-dim">{service.headline}</p>

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {service.metrics.map(([label, value]) => (
          <div key={label} className="rounded-md border border-border bg-background px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-[0.1em] text-ink-faint">{label}</div>
            <div className="num mt-1 truncate text-[13px] font-semibold text-foreground">{value}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 space-y-1.5">
        {service.evidence.slice(0, 4).map((item) => (
          <div key={item} className="flex items-start gap-2 text-[11.5px] leading-snug text-ink-dim">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-foreground/40" />
            <span>{item}</span>
          </div>
        ))}
      </div>

      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        {service.actions.map((action) => {
          const ActionIcon = action.icon ?? Settings2;
          return (
            <Button
              key={action.label}
              type="button"
              size="sm"
              variant={action.variant ?? "outline"}
              disabled={action.disabled}
              onClick={action.onClick}
            >
              <ActionIcon className="size-3.5" />
              {action.label}
            </Button>
          );
        })}
      </div>
    </article>
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

function RunResearchTable({ steps }: { steps: AgentStep[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] text-left text-[12px]">
        <thead className="border-b border-border text-[10px] uppercase tracking-[0.12em] text-ink-faint">
          <tr>
            <th className="pb-3 pr-3 font-medium">Section</th>
            <th className="pb-3 pr-3 font-medium">Status</th>
            <th className="pb-3 pr-3 font-medium">Summary</th>
            <th className="pb-3 pr-3 font-medium">Metrics</th>
            <th className="pb-3 font-medium">MongoDB artifacts</th>
          </tr>
        </thead>
        <tbody>
          {steps.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-10 text-center text-ink-faint">
                Run the pipeline to populate researched details.
              </td>
            </tr>
          ) : (
            steps.map((step) => {
              const Icon = STEP_ICONS[step.key];
              return (
                <tr key={step.key} className="border-b border-border/70 last:border-0">
                  <td className="py-3 pr-3">
                    <div className="flex items-center gap-2">
                      <Icon className="size-4 shrink-0" style={{ color: STEP_COLORS[step.key] }} />
                      <div>
                        <div className="font-medium text-foreground">{STEP_LABELS[step.key]}</div>
                        <div className="text-[10.5px] text-ink-faint">{step.role}</div>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 pr-3">
                    <Badge variant={step.status === "success" || step.status === "ready" ? "secondary" : "outline"}>{step.status}</Badge>
                  </td>
                  <td className="py-3 pr-3 text-ink-dim">{step.summary}</td>
                  <td className="py-3 pr-3">
                    <div className="flex flex-wrap gap-1.5">
                      {step.metrics.map((metric) => (
                        <span key={metric.label} className="rounded border border-border bg-background px-2 py-1 text-[10.5px] text-ink-dim">
                          {metric.label}: <span className="num text-foreground">{formatMetric(metric)}</span>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {step.artifacts.map((artifact) => (
                        <span key={artifact} className="rounded border border-border bg-background px-2 py-1 text-[10.5px] text-ink-dim">
                          {artifact}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

function AgentIntelligenceMap({
  data,
  resources,
  proposals,
  activity,
}: {
  data: CommandRun | undefined;
  resources: ResourceItem[];
  proposals: Proposal[];
  activity: AgentActivityEntry[];
}) {
  const rows = [
    {
      agent: "Monitor",
      reads: "AWS collectors, FOCUS rows, resource tags, service inventory",
      analysis: `${resources.length} resources normalized across ${new Set(resources.map((resource) => resource.resource_type ?? resource.type)).size} resource types`,
      writes: "resources, focus_records, cloud_snapshot, agent_runs",
      signal: latestActivity(activity, "Monitor")?.message ?? "Waiting for next monitor run",
    },
    {
      agent: "Analyzer",
      reads: "Resource inventory, utilization, cost, security posture, tag coverage",
      analysis: `${data?.summary.findings ?? 0} findings with idle, security, storage, database, and governance checks`,
      writes: "findings, analyzer score output, anomaly and risk context",
      signal: latestActivity(activity, "Analyzer")?.message ?? "Waiting for analyzer output",
    },
    {
      agent: "Decision",
      reads: "Findings, business rules, service boundaries, proposal templates",
      analysis: `${proposals.length} proposals mapped to actions, risks, evidence, rollback plans, and approval state`,
      writes: "proposals, approval candidates, blocked decisions",
      signal: latestActivity(activity, "Decision")?.message ?? "Waiting for decision output",
    },
    {
      agent: "Supervisor",
      reads: "Proposal risk, human gates, approval queue, notification target",
      analysis: `${proposals.filter((proposal) => proposal.status === "pending_approval").length} pending approvals and ${proposals.filter((proposal) => proposal.status === "blocked").length} blocked items`,
      writes: "approval state, email receipts, approval tokens",
      signal: latestActivity(activity, "Supervisor")?.message ?? "Waiting for supervisor output",
    },
    {
      agent: "Executor",
      reads: "Approved proposals, live AWS state, execution safety gates",
      analysis: `${data?.summary.executed_or_simulated ?? 0} executed/simulated, ${data?.summary.blocked_or_refused ?? 0} blocked/refused`,
      writes: "execution_audit, rollback descriptors, verification status",
      signal: latestActivity(activity, "Executor")?.message ?? "Waiting for executor output",
    },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[980px] text-left text-[12px]">
        <thead className="border-b border-border text-[10px] uppercase tracking-[0.12em] text-ink-faint">
          <tr>
            <th className="pb-3 pr-3 font-medium">Agent</th>
            <th className="pb-3 pr-3 font-medium">Reads</th>
            <th className="pb-3 pr-3 font-medium">Analysis</th>
            <th className="pb-3 pr-3 font-medium">Writes</th>
            <th className="pb-3 font-medium">Latest signal</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.agent} className="border-b border-border/70 last:border-0 align-top">
              <td className="py-3 pr-3 font-semibold text-foreground">{row.agent}</td>
              <td className="py-3 pr-3 text-ink-dim">{row.reads}</td>
              <td className="py-3 pr-3 text-ink-dim">{row.analysis}</td>
              <td className="py-3 pr-3 text-ink-dim">{row.writes}</td>
              <td className="py-3 text-ink-dim">{row.signal}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function controlPolicyFor(resource: ResourceItem) {
  const type = resource.resource_type ?? resource.type ?? "unknown";
  if (type === "ec2_instance") return "Live start/stop enabled through Executor audit";
  if (type === "ebs_volume") return "Research enabled; delete requires proposal approval and snapshot evidence";
  if (type === "rds_instance") return "Research enabled; no direct DB mutation from this control";
  if (type === "dynamodb_table") return "Research enabled; table mutations blocked without explicit proposal";
  if (type === "lambda_function") return "Research enabled; Lambda write policy is not configured";
  if (type === "s3_bucket") return "Research enabled; lifecycle suggestions only, no delete or policy mutation";
  if (type === "vpc" || type === "security_group") return "Research enabled; network/security changes require review";
  return "Research enabled";
}

function ResourceResearchTable({
  resources,
  onInspect,
  onEc2Power,
  powerBusyId,
}: {
  resources: ResourceItem[];
  onInspect: (resource: ResourceItem) => void;
  onEc2Power: (resource: ResourceItem, action: Ec2PowerAction) => void;
  powerBusyId: string | null;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1360px] text-left text-[12px]">
        <thead className="border-b border-border text-[10px] uppercase tracking-[0.12em] text-ink-faint">
          <tr>
            <th className="pb-3 pr-3 font-medium">Resource</th>
            <th className="pb-3 pr-3 font-medium">Service</th>
            <th className="pb-3 pr-3 font-medium">Hardware</th>
            <th className="pb-3 pr-3 font-medium">State</th>
            <th className="pb-3 pr-3 font-medium">Cost</th>
            <th className="pb-3 pr-3 font-medium">FOCUS research</th>
            <th className="pb-3 pr-3 font-medium">Owner/env</th>
            <th className="pb-3 pr-3 font-medium">Tags</th>
            <th className="pb-3 font-medium">Live control</th>
          </tr>
        </thead>
        <tbody>
          {resources.length === 0 ? (
            <tr>
              <td colSpan={9} className="py-10 text-center text-ink-faint">
                No resource inventory returned yet.
              </td>
            </tr>
          ) : (
            resources.map((resource) => {
              const hardware = hardwareForResource(resource);
              return (
                <tr key={`${resource.resource_type ?? resource.type}-${resource.id}`} className="border-b border-border/70 last:border-0 align-top">
                  <td className="py-3 pr-3">
                    <div className="num font-medium text-foreground">{resource.id}</div>
                    <div className="num mt-0.5 text-[10.5px] text-ink-faint">{resource.region}</div>
                  </td>
                  <td className="py-3 pr-3">
                    <div className="font-medium text-foreground">{serviceLabelForResource(resource)}</div>
                    <div className="num mt-0.5 text-[10.5px] text-ink-faint">{resource.resource_type ?? resource.type}</div>
                  </td>
                  <td className="num py-3 pr-3 text-ink-dim">
                    {hardware.instanceType ? (
                      <>
                        <div>{hardware.instanceType}</div>
                        <div className="mt-0.5 text-[10.5px] text-ink-faint">
                          {hardware.ram ?? "-"} GiB RAM / {hardware.vcpu ?? "-"} vCPU
                        </div>
                      </>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="py-3 pr-3">
                    <Badge variant={resource.status === "Healthy" ? "secondary" : "outline"}>{resource.state ?? resource.status}</Badge>
                  </td>
                  <td className="num py-3 pr-3 text-ink-dim">{resourceCostText(resource.monthly_cost_usd)}</td>
                  <td className="py-3 pr-3 text-ink-dim">
                    <div>{resource.cost_source}</div>
                    <div className="num mt-0.5 text-[10.5px] text-ink-faint">
                      {resource.focus_row_count} rows / {resource.focus_dataset_id ?? "no dataset"}
                    </div>
                  </td>
                  <td className="py-3 pr-3 text-ink-dim">
                    <div>{resource.owner ?? "unknown"}</div>
                    <div className="mt-0.5 text-[10.5px] text-ink-faint">{resource.environment}</div>
                  </td>
                  <td className="py-3 pr-3 text-ink-dim">{compactTags(resource.tags)}</td>
                  <td className="py-3">
                    <div className="flex min-w-[230px] flex-wrap gap-1.5">
                      <Button type="button" size="sm" variant="outline" onClick={() => onInspect(resource)}>
                        <FileSearch className="size-3.5" />
                        Research
                      </Button>
                      {isEc2Resource(resource) ? (
                        <>
                          <Button
                            type="button"
                            size="sm"
                            variant={(resource.state ?? "").startsWith("running") ? "destructive" : "outline"}
                            disabled={powerBusyId === resource.id || !(resource.state ?? "").startsWith("running")}
                            onClick={() => onEc2Power(resource, "stop")}
                          >
                            {powerBusyId === resource.id ? <Gauge className="size-3.5 animate-spin" /> : <StopCircle className="size-3.5" />}
                            Stop
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant={(resource.state ?? "").startsWith("stopped") ? "default" : "outline"}
                            disabled={powerBusyId === resource.id || !(resource.state ?? "").startsWith("stopped")}
                            onClick={() => onEc2Power(resource, "start")}
                          >
                            {powerBusyId === resource.id ? <Gauge className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                            Start
                          </Button>
                        </>
                      ) : (
                        <Badge variant={resource.resource_type === "lambda_function" ? "destructive" : "outline"}>
                          {resource.resource_type === "lambda_function" ? "Needs Lambda policy" : "Research only"}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-1.5 max-w-[260px] text-[10.5px] leading-snug text-ink-faint">
                      {controlPolicyFor(resource)}
                    </div>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

function ActivityLogTable({ entries }: { entries: AgentActivityEntry[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[780px] text-left text-[12px]">
        <thead className="border-b border-border text-[10px] uppercase tracking-[0.12em] text-ink-faint">
          <tr>
            <th className="pb-3 pr-3 font-medium">Log</th>
            <th className="pb-3 pr-3 font-medium">Status</th>
            <th className="pb-3 pr-3 font-medium">Duration</th>
            <th className="pb-3 font-medium">Message</th>
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 ? (
            <tr>
              <td colSpan={4} className="py-10 text-center text-ink-faint">
                No agent activity logs returned yet.
              </td>
            </tr>
          ) : (
            entries.slice(0, 12).map((entry) => (
              <tr key={entry.id} className="border-b border-border/70 last:border-0">
                <td className="py-3 pr-3">
                  <div className="font-medium text-foreground">{entry.agent}</div>
                  <div className="num mt-0.5 text-[10.5px] text-ink-faint">{entry.timestamp}</div>
                </td>
                <td className="py-3 pr-3">
                  <Badge variant={entry.status === "success" ? "secondary" : "destructive"}>{entry.status}</Badge>
                </td>
                <td className="num py-3 pr-3 text-ink-dim">{entry.duration_ms} ms</td>
                <td className="py-3 text-ink-dim">{entry.message}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function AgentCommandPage() {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<Provider>("aws");
  const [showPayload, setShowPayload] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const [nextSyncAt, setNextSyncAt] = useState(() => Date.now() + AUTO_SYNC_MS);
  const [selectedTagKey, setSelectedTagKey] = useState("Environment");
  const [selectedTagValue, setSelectedTagValue] = useState("all");
  const [selectedResource, setSelectedResource] = useState<ResourceItem | null>(null);

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

  const resourcesQuery = useResources(undefined, { refetchInterval: AUTO_SYNC_MS });
  const proposalsQuery = useProposals({ refetchInterval: AUTO_SYNC_MS });
  const governanceQuery = useIamGovernance({ refetchInterval: AUTO_SYNC_MS });
  const activityQuery = useAgentActivity(100);
  const coreServicesQuery = useQuery({
    queryKey: ["aws-core-services"],
    queryFn: () => api.get<AwsCoreServicesExternalFactor>("/v1/external-factors/aws-core-services"),
    refetchInterval: AUTO_SYNC_MS,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
  });
  const sqsStatusQuery = useQuery({
    queryKey: ["sqs-status"],
    queryFn: () => api.get<SqsStatus>("/v1/sqs/status"),
    refetchInterval: 10_000,
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
      queryClient.invalidateQueries({ queryKey: ["iam-governance"] });
      queryClient.invalidateQueries({ queryKey: ["aws-core-services"] });
      queryClient.invalidateQueries({ queryKey: ["sqs-status"] });
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

  const activeRunId = latestQuery.data?.run_id ?? runMutation.data?.run_id;
  const runActivityQuery = useQuery({
    queryKey: ["agent-activity", activeRunId, 100],
    queryFn: () => api.get<AgentActivityEntry[]>(`/v1/agent-activity?limit=100&run_id=${activeRunId}`),
    enabled: Boolean(activeRunId),
    refetchInterval: AUTO_SYNC_MS,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
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
      queryClient.invalidateQueries({ queryKey: ["sqs-status"] });
    },
    onError: (err) => {
      toast.error(isApiError(err) ? err.message : "Could not stop this EC2 instance.");
    },
  });

  const ec2PowerMutation = useMutation({
    mutationFn: ({ instanceId, action }: { instanceId: string; action: Ec2PowerAction }) =>
      api.post<ExecutionResult>(`/v1/agent-command/ec2-instances/${instanceId}/${action}`, { confirm: true }),
    onSuccess: (result, variables) => {
      setNextSyncAt(Date.now() + AUTO_SYNC_MS);
      const status = result.execution.status ?? result.execution.execution_status;
      if (status === "executed" || status === "no_op") {
        toast.success(status === "no_op" ? `Instance already ${variables.action === "start" ? "running" : "stopped"}.` : `Instance ${variables.action} requested.`);
      } else {
        toast.error(result.execution.reason_codes?.join(", ") || `${variables.action} ${status ?? "did not complete"}.`);
      }
      queryClient.invalidateQueries({ queryKey: ["agent-command-ec2-instances"] });
      queryClient.invalidateQueries({ queryKey: ["agent-command-latest"] });
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
      queryClient.invalidateQueries({ queryKey: ["sqs-status"] });
    },
    onError: (err, variables) => {
      toast.error(isApiError(err) ? err.message : `Could not ${variables.action} this EC2 instance.`);
    },
  });

  const data = latestQuery.data ?? runMutation.data;
  const steps = data?.steps ?? [];
  const resources = useMemo<ResourceItem[]>(() => resourcesQuery.data ?? [], [resourcesQuery.data]);
  const allProposals = useMemo(() => proposalsQuery.data ?? data?.proposals ?? [], [data?.proposals, proposalsQuery.data]);
  const activity = useMemo(() => activityQuery.data ?? [], [activityQuery.data]);
  const governance = governanceQuery.data;
  const proposals = useMemo(() => data?.proposals ?? allProposals, [allProposals, data?.proposals]);
  const instanceSavingsRows = useMemo(
    () => {
      const rows = new Map<
        string,
        {
          instanceId: string;
          name: string;
          tags: Record<string, string>;
          tagValue: string;
          savings: number;
          actions: Set<string>;
          risk: Proposal["risk_level"];
        }
      >();

      for (const proposal of proposals.filter((item) => isInstanceProposal(item) && proposalSavings(item) > 0)) {
        const instanceId = proposalInstanceId(proposal);
        const tags = proposalTags(proposal);
        const currentTagValue = tagValue(tags, selectedTagKey);
        const key = `${instanceId}|${currentTagValue}`;
        const existing = rows.get(key);
        if (existing) {
          existing.savings += proposalSavings(proposal);
          existing.actions.add(proposal.action_type);
          existing.risk = higherRisk(existing.risk, proposal.risk_level);
        } else {
          rows.set(key, {
            instanceId,
            name: proposalResourceName(proposal),
            tags,
            tagValue: currentTagValue,
            savings: proposalSavings(proposal),
            actions: new Set([proposal.action_type]),
            risk: proposal.risk_level,
          });
        }
      }

      return Array.from(rows.values())
        .filter((row) => selectedTagValue === "all" || row.tagValue === selectedTagValue)
        .sort((a, b) => b.savings - a.savings);
    },
    [proposals, selectedTagKey, selectedTagValue],
  );
  const tagKeys = useMemo(() => {
    const keys = new Map<string, string>();
    for (const proposal of proposals.filter(isInstanceProposal)) {
      for (const key of Object.keys(proposalTags(proposal))) {
        const normalized = key.toLowerCase();
        if (!keys.has(normalized)) keys.set(normalized, key);
      }
    }
    return Array.from(keys.values()).sort((a, b) => a.localeCompare(b));
  }, [proposals]);
  const tagValues = useMemo(() => {
    const values = new Set<string>();
    for (const proposal of proposals.filter(isInstanceProposal)) {
      values.add(tagValue(proposalTags(proposal), selectedTagKey));
    }
    return Array.from(values).sort((a, b) => {
      if (a === "untagged") return 1;
      if (b === "untagged") return -1;
      return a.localeCompare(b);
    });
  }, [proposals, selectedTagKey]);
  const selectedTagSavings = instanceSavingsRows.reduce((sum, row) => sum + row.savings, 0);
  const chart = data?.chart?.length ? data.chart : [{ stage: "Ready", savings: 0 }];
  const pending = proposals.filter((proposal) => proposal.status === "pending_approval");
  const loading = latestQuery.isLoading && !runMutation.data;
  const running = runMutation.isPending;
  const syncing =
    (latestQuery.isFetching ||
      instancesQuery.isFetching ||
      resourcesQuery.isFetching ||
      proposalsQuery.isFetching ||
      governanceQuery.isFetching ||
      coreServicesQuery.isFetching ||
      sqsStatusQuery.isFetching ||
      runActivityQuery.isFetching ||
      activityQuery.isFetching) &&
    !loading &&
    !running;
  const instances = instancesQuery.data ?? [];
  const powerBusyId = ec2PowerMutation.isPending ? ec2PowerMutation.variables?.instanceId ?? null : null;
  const analysisEmail = data?.notifications?.agent_command_analysis_email;
  const countdown = formatCountdown(nextSyncAt - now);
  const pendingApprovals = allProposals.filter((proposal) => proposal.status === "pending_approval");
  const executableProposals = allProposals.filter((proposal) => proposal.status === "approved" || proposal.status === "queued_for_execution");
  const liveAwsServices = coreServicesQuery.data?.services ?? [];
  const runActivity = runActivityQuery.data ?? [];
  const persistedArtifacts = Array.from(new Set(steps.flatMap((step) => step.artifacts))).sort((a, b) => a.localeCompare(b));
  const failedLogs = runActivity.filter((entry) => entry.status === "failed");
  const mongoStateRows: Array<[string, unknown]> = [
    ["Run collection", "agent_command_runs"],
    ["Run saved", data?.run_id && !data.persistence_error ? "yes" : data?.persistence_error ? "degraded" : "waiting"],
    ["Run id", data?.run_id],
    ["Created", data?.created_at],
    ["Finished", data?.finished_at],
    ["Activity collection", "agent_runs"],
    ["Run logs", runActivity.length],
    ["Failed logs", failedLogs.length],
    ["Notification receipt", analysisEmail ? "stored with latest run" : "waiting"],
    ["Persistence error", data?.persistence_error],
  ];
  const researchRows: Array<[string, unknown]> = [
    ["Provider", data?.provider ?? provider],
    ["Account", data?.account_id],
    ["Region", data?.region],
    ["Resources researched", data?.summary.resources ?? resources.length],
    ["Findings", data?.summary.findings ?? 0],
    ["Proposals", proposals.length],
    ["Pending approval", data?.summary.pending_approvals ?? pending.length],
    ["Blocked", data?.summary.blocked ?? 0],
    ["Potential monthly savings", formatMoneyParts(data?.summary.potential_monthly_savings ?? projectedProposalSavings(proposals)).usd],
    ["FOCUS source", data?.focus_source],
    ["FOCUS dataset", data?.focus_dataset_id],
    ["FOCUS rows", data?.focus_row_count ?? 0],
  ];
  const commandServices: ServiceCommand[] = (() => {
    const monitorActivity = latestActivity(activity, "Monitor");
    const analyzerActivity = latestActivity(activity, "Analyzer");
    const decisionActivity = latestActivity(activity, "Decision");
    const supervisorActivity = latestActivity(activity, "Supervisor");
    const executorActivity = latestActivity(activity, "Executor");
    const focusRows = data?.focus_row_count ?? resources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0);
    const riskyIamUsers = (governance?.users ?? []).filter((user) => (user.access_key_age_days ?? 0) > 90 || user.policies.length > 0);

    return [
      {
        key: "pipeline",
        title: "Five-agent FinOps pipeline",
        group: "Core",
        status: running ? "waiting" : serviceStatus(Boolean(data?.run_id), latestQuery.isLoading, latestQuery.isError),
        icon: Bot,
        headline: "Runs Monitor, Analyzer, Decision, Supervisor, and Executor ledger refresh in one backend command.",
        metrics: [
          ["Run", data?.run_id ? data.run_id.slice(0, 8) : "none"],
          ["Status", running ? "running" : data?.status ?? "waiting"],
          ["Findings", data?.summary.findings ?? 0],
          ["Proposals", allProposals.length],
        ],
        evidence: [
          `Latest response: /v1/agent-command/latest`,
          `Command route: POST /v1/agent-command/run?provider=${provider}`,
          `Last activity: ${monitorActivity ? shortTimestamp(monitorActivity.timestamp) : "waiting"}`,
        ],
        actions: [
          {
            label: running ? "Running" : "Run all agents",
            onClick: () => runMutation.mutate(),
            disabled: running,
            icon: running ? Gauge : Play,
          },
          { label: "Refresh", onClick: refreshAll, disabled: syncing || running, icon: RefreshCw, variant: "outline" },
        ],
      },
      {
        key: "resources",
        title: "AWS resource inventory",
        group: "Discovery",
        status: serviceStatus(resources.length > 0, resourcesQuery.isLoading, resourcesQuery.isError),
        icon: Cloud,
        headline: "Shows every monitored resource returned by the backend inventory route, not a frontend template list.",
        metrics: [
          ["Resources", resources.length],
          ["Types", new Set(resources.map((resource) => resource.type)).size],
          ["FOCUS rows", focusRows],
          ["Live costed", resources.filter((resource) => resource.cost_source === "focus_live_export").length],
        ],
        evidence: [
          "Reads GET /v1/resources",
          `${resources.filter((resource) => resource.status === "At-risk").length} resources currently marked at-risk`,
          `${resources.filter((resource) => resource.monthly_cost_usd != null).length} resources have backend cost values`,
        ],
        actions: [
          { label: "Refresh inventory", onClick: () => void resourcesQuery.refetch(), disabled: resourcesQuery.isFetching, icon: RefreshCw },
          { label: "Run collector", onClick: () => runMutation.mutate(), disabled: running, icon: RadioTower },
        ],
      },
      {
        key: "aws-services",
        title: "AWS service coverage",
        group: "Catalog",
        status: serviceStatus(liveAwsServices.length > 0, coreServicesQuery.isLoading, coreServicesQuery.isError),
        icon: Network,
        headline: "Maps each supported AWS service to collectors, IAM policies, approved executor actions, and blocked actions.",
        metrics: [
          ["Services", liveAwsServices.length],
          ["Read actions", liveAwsServices.reduce((sum, service) => sum + service.collector_actions.length, 0)],
          ["Executor actions", liveAwsServices.reduce((sum, service) => sum + service.approved_executor_actions.length, 0)],
          ["Rules", liveAwsServices.reduce((sum, service) => sum + service.rules.length, 0)],
        ],
        evidence: [
          "Reads GET /v1/external-factors/aws-core-services",
          `${liveAwsServices.filter((service) => service.inventory_status === "implemented").length} services implemented by backend catalog`,
          `Source: ${coreServicesQuery.data?.source ?? "waiting"}`,
        ],
        actions: [
          { label: "Refresh catalog", onClick: () => void coreServicesQuery.refetch(), disabled: coreServicesQuery.isFetching, icon: RefreshCw },
        ],
      },
      {
        key: "iam",
        title: "IAM governance and creators",
        group: "Security",
        status: serviceStatus(Boolean(governance), governanceQuery.isLoading, governanceQuery.isError || Boolean(Object.keys(governance?.errors ?? {}).length)),
        icon: KeyRound,
        headline: "Connects IAM users, attached policies, root posture, and CloudTrail creator events for user-wise accountability.",
        metrics: [
          ["Users", governance?.users.length ?? 0],
          ["Creators", governance?.resource_creators.length ?? 0],
          ["Risk users", riskyIamUsers.length],
          ["Errors", Object.keys(governance?.errors ?? {}).length],
        ],
        evidence: [
          "Reads GET /v1/governance/iam-overview",
          `Root MFA: ${governance?.account.root_mfa_enabled == null ? "unknown" : governance.account.root_mfa_enabled ? "enabled" : "disabled"}`,
          `Lookback: ${governance?.resource_creators_lookback_days ?? 0} days`,
        ],
        actions: [
          { label: "Refresh IAM", onClick: () => void governanceQuery.refetch(), disabled: governanceQuery.isFetching, icon: RefreshCw },
        ],
      },
      {
        key: "approvals",
        title: "Supervisor approvals",
        group: "Control",
        status: serviceStatus(allProposals.length > 0, proposalsQuery.isLoading, proposalsQuery.isError),
        icon: ShieldCheck,
        headline: "Tracks proposal status from suggested savings through human approval and execution eligibility.",
        metrics: [
          ["All proposals", allProposals.length],
          ["Pending", pendingApprovals.length],
          ["Approved queue", executableProposals.length],
          ["Blocked", allProposals.filter((proposal) => proposal.status === "blocked" || proposal.status === "rejected").length],
        ],
        evidence: [
          "Reads GET /v1/approvals?status=",
          `${formatMoneyParts(projectedProposalSavings(allProposals)).usd} projected from approved or pending proposals`,
          `${pendingApprovals.length} proposals waiting for human decision`,
        ],
        actions: [
          { label: "Refresh proposals", onClick: () => void proposalsQuery.refetch(), disabled: proposalsQuery.isFetching, icon: RefreshCw },
          { label: "Run decision", onClick: () => runMutation.mutate(), disabled: running, icon: BrainCircuit },
        ],
      },
      {
        key: "sqs",
        title: "SQS execution queue",
        group: "Async",
        status: sqsStatusQuery.isError || Boolean(sqsStatusQuery.data?.last_error) ? "needs_attention" : sqsStatusQuery.data?.enabled && sqsStatusQuery.data?.queue_url_configured ? "live" : "waiting",
        icon: Workflow,
        headline: "Shows whether approved actions can move through the backend queue before the executor mutates AWS.",
        metrics: [
          ["Enabled", sqsStatusQuery.data?.enabled ? "yes" : "no"],
          ["Worker", sqsStatusQuery.data?.running ? "running" : "stopped"],
          ["Processed", sqsStatusQuery.data?.processed_total ?? 0],
          ["Region", sqsStatusQuery.data?.region ?? data?.region ?? "unknown"],
        ],
        evidence: [
          "Reads GET /v1/sqs/status",
          `Queue URL configured: ${sqsStatusQuery.data?.queue_url_configured ? "yes" : "no"}`,
          `Last poll: ${shortTimestamp(sqsStatusQuery.data?.last_poll_at ?? undefined)}`,
          sqsStatusQuery.data?.last_error ? `Last error: ${sqsStatusQuery.data.last_error}` : "No queue error returned",
        ],
        actions: [
          { label: "Refresh queue", onClick: () => void sqsStatusQuery.refetch(), disabled: sqsStatusQuery.isFetching, icon: RefreshCw },
        ],
      },
      {
        key: "notifications",
        title: "Brevo analysis email",
        group: "Notify",
        status: analysisEmail?.sent ? "live" : analysisEmail?.attempted ? "needs_attention" : "waiting",
        icon: Bell,
        headline: "Confirms whether command-run analysis emails were attempted and delivered through the configured notification provider.",
        metrics: [
          ["Attempted", analysisEmail?.attempted ? "yes" : "no"],
          ["Sent", analysisEmail?.sent ? "yes" : "no"],
          ["Provider", analysisEmail?.provider ?? "waiting"],
          ["Recipient", analysisEmail?.recipient ?? "not set"],
        ],
        evidence: [emailStatusText(analysisEmail), "Email status is returned inside /v1/agent-command/latest"],
        actions: [
          { label: "Run and email", onClick: () => runMutation.mutate(), disabled: running, icon: MailCheck },
        ],
      },
      {
        key: "activity",
        title: "Agent activity logs",
        group: "Audit",
        status: serviceStatus(activity.length > 0, activityQuery.isLoading, activityQuery.isError),
        icon: FileSearch,
        headline: "Streams the last command outcomes, durations, statuses, and raw payloads from the backend activity ledger.",
        metrics: [
          ["Logs", activity.length],
          ["Success", activity.filter((entry) => entry.status === "success").length],
          ["Failed", activity.filter((entry) => entry.status === "failed").length],
          ["Latest", activity[0] ? shortTimestamp(activity[0].timestamp) : "waiting"],
        ],
        evidence: [
          "Reads GET /v1/agent-activity?limit=100",
          `Analyzer: ${analyzerActivity?.status ?? "waiting"}`,
          `Decision: ${decisionActivity?.status ?? "waiting"}`,
          `Supervisor: ${supervisorActivity?.status ?? "waiting"}`,
          `Executor: ${executorActivity?.status ?? "waiting"}`,
        ],
        actions: [
          { label: "Refresh logs", onClick: () => void activityQuery.refetch(), disabled: activityQuery.isFetching, icon: RefreshCw },
        ],
      },
      {
        key: "executor",
        title: "Live EC2 executor",
        group: "Action",
        status: serviceStatus(instances.length > 0, instancesQuery.isLoading, instancesQuery.isError),
        icon: Server,
        headline: "Lists live EC2 instances from AWS and exposes the guarded stop path already wired to executor audit records.",
        metrics: [
          ["Instances", instances.length],
          ["Running", instances.filter((instance) => instance.state === "running").length],
          ["Stopped", instances.filter((instance) => instance.state === "stopped").length],
          ["Region", instances[0]?.region ?? data?.region ?? "unknown"],
        ],
        evidence: [
          "Reads GET /v1/agent-command/ec2-instances",
          "Stop action calls POST /v1/agent-command/ec2-instances/{instance_id}/stop",
          `${instances.filter((instance) => instance.state === "running").length} instances are currently stoppable`,
        ],
        actions: [
          { label: "Refresh EC2", onClick: () => void instancesQuery.refetch(), disabled: instancesQuery.isFetching, icon: RefreshCw },
        ],
      },
    ];
  })();

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

  useEffect(() => {
    if (!tagKeys.length) return;
    if (!tagKeys.some((key) => key.toLowerCase() === selectedTagKey.toLowerCase())) {
      setSelectedTagKey(tagKeys[0]);
      setSelectedTagValue("all");
    }
  }, [selectedTagKey, tagKeys]);

  useEffect(() => {
    if (selectedTagValue === "all") return;
    if (!tagValues.includes(selectedTagValue)) setSelectedTagValue("all");
  }, [selectedTagValue, tagValues]);

  function refreshAll() {
    setNextSyncAt(Date.now() + AUTO_SYNC_MS);
    void latestQuery.refetch();
    void instancesQuery.refetch();
    void runActivityQuery.refetch();
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

      <div className="mt-5">
        <Panel
          title="All Service Commands"
          eyebrow="Runtime control"
          subtitle="Every card below is backed by the live frontend API client and the backend services already wired into CloudCare."
          delay={120}
        >
          <div className="grid gap-3 xl:grid-cols-2 2xl:grid-cols-3">
            {commandServices.map((service) => (
              <ServiceCommandCard key={service.key} service={service} />
            ))}
          </div>
        </Panel>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Panel title="Research Details" eyebrow="Run evidence" subtitle="The latest command output grouped by the actual data reviewed and produced." delay={140}>
          <DetailRows rows={researchRows} />
        </Panel>

        <Panel title="MongoDB Save State" eyebrow="Persistence" subtitle="Run payload, activity logs, proposal state, notification receipt, and executor audit storage." delay={150}>
          <DetailRows rows={mongoStateRows} />
          <div className="mt-4 flex flex-wrap gap-1.5">
            {(persistedArtifacts.length ? persistedArtifacts : ["agent_command_runs", "agent_runs"]).map((artifact) => (
              <span key={artifact} className="rounded border border-border bg-background px-2 py-1 text-[10.5px] text-ink-dim">
                {artifact}
              </span>
            ))}
          </div>
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Pipeline Research Output" eyebrow="Detailed stages" subtitle="Detailed outputs without the individual agent card layout." delay={155}>
          <RunResearchTable steps={steps} />
        </Panel>
      </div>

      <div className="mt-5">
        <Panel
          title="Agent Intelligence Map"
          eyebrow="Reads / analysis / writes"
          subtitle="What each agent researched, how it interpreted the data, and which MongoDB artifacts it produces."
          delay={156}
        >
          <AgentIntelligenceMap data={data} resources={resources} proposals={proposals} activity={runActivity.length ? runActivity : activity} />
        </Panel>
      </div>

      <div className="mt-5">
        <Panel
          title="All Resource Research Inventory"
          eyebrow="Live AWS + FOCUS detail"
          subtitle="Every resource currently returned to Agent Command, including service classification, hardware, cost source, ownership, environment, and tags."
          delay={157}
        >
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{resources.length} resources</Badge>
              <Badge variant="outline">{new Set(resources.map((resource) => resource.resource_type ?? resource.type)).size} types</Badge>
              <Badge variant="outline">{resources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0)} FOCUS rows</Badge>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={resourcesQuery.isFetching}
              onClick={() => resourcesQuery.refetch()}
            >
              <RefreshCw className={resourcesQuery.isFetching ? "size-3.5 animate-spin" : "size-3.5"} />
              Refresh resources
            </Button>
          </div>
          <ResourceResearchTable
            resources={resources}
            powerBusyId={powerBusyId}
            onInspect={setSelectedResource}
            onEc2Power={(resource, action) => {
              const verb = action === "start" ? "Start" : "Stop";
              if (window.confirm(`${verb} ${resource.id}?`)) {
                ec2PowerMutation.mutate({ instanceId: resource.id, action });
              }
            }}
          />
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="MongoDB Activity Logs" eyebrow="agent_runs" subtitle="Run-scoped log documents returned by /v1/agent-activity for the latest command." delay={158}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{runActivity.length} logs</Badge>
              <Badge variant={failedLogs.length ? "destructive" : "secondary"}>{failedLogs.length} failed</Badge>
              <Badge variant="outline">{activeRunId ? `Run ${activeRunId.slice(0, 8)}` : "No run selected"}</Badge>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={!activeRunId || runActivityQuery.isFetching}
              onClick={() => runActivityQuery.refetch()}
            >
              <RefreshCw className={runActivityQuery.isFetching ? "size-3.5 animate-spin" : "size-3.5"} />
              Refresh logs
            </Button>
          </div>
          <ActivityLogTable entries={runActivity} />
        </Panel>
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

        <Panel title="Tag Savings" eyebrow="Instances" subtitle="EC2 savings ranked by the selected tag key and value." delay={180}>
          <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(180px,0.7fr)_minmax(0,1.3fr)]">
            <div className="rounded-md border border-border bg-background px-3 py-2.5">
              <label className="text-[10px] uppercase tracking-[0.12em] text-ink-faint" htmlFor="tag-key">
                Tag key
              </label>
              <select
                id="tag-key"
                className="mt-2 w-full rounded border border-border bg-card px-2 py-1.5 text-[12px] text-foreground outline-none"
                value={selectedTagKey}
                onChange={(event) => {
                  setSelectedTagKey(event.target.value);
                  setSelectedTagValue("all");
                }}
              >
                {(tagKeys.length ? tagKeys : ["Environment"]).map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </div>
            <div className="rounded-md border border-border bg-background px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Selected savings</div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <div className="num text-[1.45rem] font-semibold leading-none text-foreground">
                  {formatMoneyParts(selectedTagSavings).usd}
                </div>
                <Badge variant="outline">
                  <Tags className="size-3" />
                  {instanceSavingsRows.length} instances
                </Badge>
              </div>
            </div>
          </div>

          <div className="mb-3 flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant={selectedTagValue === "all" ? "default" : "outline"}
              onClick={() => setSelectedTagValue("all")}
            >
              All
            </Button>
            {tagValues.map((value) => (
              <Button
                key={value}
                type="button"
                size="sm"
                variant={selectedTagValue === value ? "default" : "outline"}
                onClick={() => setSelectedTagValue(value)}
              >
                {value}
              </Button>
            ))}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-[12px]">
              <thead className="border-b border-border text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                <tr>
                  <th className="pb-3 pr-3 font-medium">Instance</th>
                  <th className="pb-3 pr-3 font-medium">Tag value</th>
                  <th className="pb-3 pr-3 font-medium">Action</th>
                  <th className="pb-3 pr-3 font-medium">Risk</th>
                  <th className="pb-3 text-right font-medium">Savings/mo</th>
                </tr>
              </thead>
              <tbody>
                {instanceSavingsRows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-10 text-center text-ink-faint">
                      No cost-saving EC2 proposals match this tag.
                    </td>
                  </tr>
                ) : (
                  instanceSavingsRows.map((row) => (
                    <tr key={`${row.instanceId}-${row.tagValue}`} className="border-b border-border/70 last:border-0">
                      <td className="py-3 pr-3">
                        <div className="font-medium text-foreground">{row.name}</div>
                        <div className="num mt-0.5 text-[10.5px] text-ink-faint">{row.instanceId}</div>
                      </td>
                      <td className="py-3 pr-3">
                        <Badge variant={row.tagValue === "untagged" ? "outline" : "secondary"}>{row.tagValue}</Badge>
                      </td>
                      <td className="py-3 pr-3 text-ink-dim">{Array.from(row.actions).map((action) => action.replace(/_/g, " ")).join(", ")}</td>
                      <td className="py-3 pr-3">
                        <Badge variant={row.risk === "low" ? "secondary" : "outline"}>{row.risk}</Badge>
                      </td>
                      <td className="num py-3 text-right font-semibold text-foreground">
                        {formatMoneyParts(row.savings).usd}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
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

      <ResourceDetailSheet
        resourceId={selectedResource?.id ?? null}
        resourceType={selectedResource?.resource_type ?? null}
        onOpenChange={(open) => {
          if (!open) setSelectedResource(null);
        }}
      />
    </div>
  );
}
