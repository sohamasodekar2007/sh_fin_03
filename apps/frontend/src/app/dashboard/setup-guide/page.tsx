"use client";

import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Cloud,
  KeyRound,
  MailCheck,
  PlayCircle,
  ShieldCheck,
  Tags,
  Terminal,
} from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

interface SqsStatus {
  running: boolean;
  enabled: boolean;
  queue_url_configured: boolean;
  last_poll_at: string | null;
  last_processed_at: string | null;
  last_error: string | null;
  processed_total: number;
  region: string;
}

const setupSteps = [
  {
    title: "Create the CloudCare user",
    owner: "CloudCare admin",
    status: "Required",
    detail: "Register each operator with their real CloudCare account email. Pipeline analysis emails resolve by authenticated user first, then by the stored user record, then by tenant fallback.",
  },
  {
    title: "Configure environment secrets",
    owner: "Platform owner",
    status: "Required",
    detail: "Fill the backend .env and frontend .env.local values, then restart the API process because settings are cached for the process lifetime.",
  },
  {
    title: "Connect cloud read access",
    owner: "Cloud admin",
    status: "Required",
    detail: "Use a read-only AWS role for collectors. Do not reuse the executor write role for inventory, metrics, or cost ingestion.",
  },
  {
    title: "Authorize Brevo email sending",
    owner: "Email admin",
    status: "Required",
    detail: "Verify the sender, add the API key, add SMTP credentials, and authorize the API server public IP in Brevo Security.",
  },
  {
    title: "Run in simulation first",
    owner: "FinOps lead",
    status: "Required",
    detail: "Keep live execution disabled until Monitor, Analyzer, Decision, Supervisor, and notification receipts are green.",
  },
  {
    title: "Enable live execution deliberately",
    owner: "Security approver",
    status: "Controlled",
    detail: "Only turn on live execution after resources are tagged with the allowlist tag and the executor role policy is reviewed.",
  },
] as const;

const envRows = [
  ["APP_BASE_URL", "Frontend URL used for approval links and dashboard buttons."],
  ["MONGODB_URI", "Atlas or local MongoDB connection string for users, runs, proposals, approvals, and audit records."],
  ["JWT_SECRET", "Login token signing secret. Generate a unique production value."],
  ["APPROVAL_TOKEN_SECRET", "Separate HMAC secret for one-click approval links. Must not match JWT_SECRET."],
  ["OPENAI_API_KEY", "Decision-agent and chatbot model access."],
  ["AWS_ACCOUNT_ID / AWS_REGION", "Primary account and region displayed in the dashboard and used by AWS collectors."],
  ["AWS_READ_ROLE_ARN", "Read-only collector role."],
  ["AWS_WRITE_ROLE_ARN", "Executor role used only after human approval and runtime gates."],
  ["BREVO_API_KEY", "Primary email provider path for OTP, approval, completion, and pipeline analysis messages."],
  ["SMTP_USERNAME / SMTP_PASSWORD", "Brevo SMTP fallback credentials."],
  ["SMTP_FROM", "Verified sender email in Brevo."],
  ["EXECUTION_ENABLED / EXECUTION_MODE", "Hard switch for simulation versus live action."],
  ["SQS_EXECUTION_ENABLED", "When true, approvals enqueue execution jobs instead of running inline."],
  ["SQS_EXECUTION_QUEUE_URL", "The production SQS queue URL used by the execution worker."],
] as const;

const policies = [
  {
    title: "Human approval policy",
    text: "Supervisor may mark work pending or blocked, but never approved. Only a dashboard approve button or signed approval email link can move a proposal forward.",
  },
  {
    title: "Execution allowlist policy",
    text: "Executor re-reads live AWS tags before mutation. A resource without cloudcare:managed=true, or the configured EXECUTION_ALLOWLIST_TAG, is refused in both simulation and live modes.",
  },
  {
    title: "Role separation policy",
    text: "Collectors use read access. Executor uses a dedicated write role. Root users, broad admin keys, and reused read roles are outside the operating model.",
  },
  {
    title: "Email receipt policy",
    text: "Pipeline runs return notifications.agent_command_analysis_email with attempted, sent, provider, recipient, reason, and provider errors so operators can see delivery state immediately.",
  },
  {
    title: "SQS execution policy",
    text: "Approved proposals are queued first when SQS is enabled. The worker moves them through queued_for_execution, executing, and executed/refused so the approval request never waits on AWS mutation.",
  },
  {
    title: "Data governance policy",
    text: "Team attribution surfaces untagged spend as its own governance-risk line item. Do not hide it under Unknown or blend it into shared spend.",
  },
  {
    title: "Security findings policy",
    text: "New checks are audit-only: open ingress, unencrypted EBS/RDS, public S3 exposure, and stale IAM keys produce findings without changing infrastructure.",
  },
] as const;

const awsPolicy = `{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadCurrentStateBeforeExecution",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeVolumes",
        "ec2:DescribeSnapshots",
        "ec2:DescribeTags",
        "cloudwatch:DescribeAlarms"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ManageAllowlistedInstances",
      "Effect": "Allow",
      "Action": [
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:ModifyInstanceAttribute",
        "ec2:CreateTags"
      ],
      "Resource": "arn:aws:ec2:*:<account-id>:instance/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/cloudcare:managed": "true"
        }
      }
    },
    {
      "Sid": "SnapshotAndDeleteAllowlistedVolumes",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateSnapshot",
        "ec2:DeleteVolume"
      ],
      "Resource": "arn:aws:ec2:*:<account-id>:volume/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/cloudcare:managed": "true"
        }
      }
    }
  ]
}`;

const trustPolicy = `{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<account-id>:user/<cloudcare-api-user>"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<AWS_EXTERNAL_ID>"
        }
      }
    }
  ]
}`;

const sqsPolicy = `{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudCareExecutionQueueWorkerAccess",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl"
      ],
      "Resource": "arn:aws:sqs:ap-south-1:350381001148:cloudcare-execution"
    }
  ]
}`;

const envSnippet = `APP_BASE_URL=http://localhost:3002
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>/cloudcare
JWT_SECRET=<openssl rand -hex 32>
APPROVAL_TOKEN_SECRET=<different openssl rand -hex 32>
OPENAI_API_KEY=<model-provider-key>
AWS_ACCOUNT_ID=<account-id>
AWS_REGION=ap-south-1
AWS_READ_ROLE_ARN=arn:aws:iam::<account-id>:role/CloudCareReadOnlyRole
AWS_WRITE_ROLE_ARN=arn:aws:iam::<account-id>:role/CloudCareExecutorRole
AWS_EXTERNAL_ID=<uuid>
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=<brevo-smtp-login>
SMTP_PASSWORD=<brevo-smtp-key>
SMTP_FROM=<verified-sender-email>
BREVO_API_KEY=<brevo-api-key>
EXECUTION_ENABLED=false
EXECUTION_MODE=simulation
EXECUTION_ALLOWLIST_TAG=cloudcare:managed=true
SQS_EXECUTION_ENABLED=true
SQS_EXECUTION_QUEUE_URL=https://sqs.<region>.amazonaws.com/<account-id>/cloudcare-execution
SQS_WAIT_TIME_SECONDS=20
SQS_VISIBILITY_TIMEOUT_SECONDS=300`;

const checks = [
  ["Backend health", "Open /health on the API and confirm service: cloudcare-api."],
  ["Cloud account", "Open Connected Providers and confirm AWS is validated for the expected account."],
  ["Agent command", "Run pipeline and confirm all five agents return status cards."],
  ["Email receipt", "Confirm Analysis email says Sent to <CloudCare account email> via brevo."],
  ["Approval loop", "Approve a pending proposal and confirm completion email receipt."],
  ["Execution guard", "Try an untagged resource in simulation and confirm NOT_ALLOWLISTED is refused."],
] as const;

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="max-h-[420px] overflow-auto rounded-md border border-border bg-background p-4 text-[11px] leading-relaxed text-ink-dim">
      <code>{children}</code>
    </pre>
  );
}

function MiniCard({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof ShieldCheck;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border border-border bg-background p-4">
      <div className="flex items-center gap-2">
        <Icon className="size-4 text-signal" />
        <h3 className="text-[14px] font-semibold text-foreground">{title}</h3>
      </div>
      <div className="mt-3 text-[12.5px] leading-relaxed text-ink-dim">{children}</div>
    </div>
  );
}

export default function SetupGuidePage() {
  const sqsStatusQuery = useQuery({
    queryKey: ["sqs-status"],
    queryFn: () => api.get<SqsStatus>("/v1/sqs/status"),
    refetchInterval: 10_000,
  });
  const sqs = sqsStatusQuery.data;

  return (
    <div className="mx-auto w-full max-w-[1320px]">
      <div className="stage rounded-md border border-border bg-card p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="eyebrow">New user setup</div>
            <h1 className="mt-1 text-[clamp(1.65rem,2.8vw,2.35rem)] font-bold leading-[1.02] text-foreground">
              CloudCare operating setup guide
            </h1>
            <p className="mt-3 max-w-3xl text-[13px] leading-relaxed text-ink-dim">
              Configure accounts, email, policies, approvals, and live execution checks before a team runs CloudCare against production infrastructure.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">Brevo ready</Badge>
            <Badge variant="outline">Human approval</Badge>
            <Badge variant="outline">AWS allowlist</Badge>
            <Badge variant="outline">Simulation first</Badge>
          </div>
        </div>
      </div>

      <div className="mt-5">
        <Panel title="Live SQS worker status" eyebrow="Runtime check" subtitle="This reads the API's /v1/sqs/status endpoint every 10 seconds." delay={60}>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="rounded-md border border-border bg-background p-4">
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Worker</div>
              <div className="mt-2 flex items-center gap-2 text-[13px] font-semibold text-foreground">
                <span className="inline-block size-2 rounded-full" style={{ background: sqs?.running ? "var(--mint)" : "var(--destructive)" }} />
                {sqsStatusQuery.isLoading ? "Checking" : sqs?.running ? "Running" : "Stopped"}
              </div>
            </div>
            <div className="rounded-md border border-border bg-background p-4">
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">SQS</div>
              <div className="mt-2 text-[13px] font-semibold text-foreground">
                {sqs?.enabled && sqs.queue_url_configured ? "Enabled" : "Not configured"}
              </div>
            </div>
            <div className="rounded-md border border-border bg-background p-4">
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Processed</div>
              <div className="num mt-2 text-[18px] font-semibold text-foreground">{sqs?.processed_total ?? 0}</div>
            </div>
            <div className="rounded-md border border-border bg-background p-4">
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Region</div>
              <div className="num mt-2 text-[13px] font-semibold text-foreground">{sqs?.region ?? "unknown"}</div>
            </div>
          </div>
          {sqs?.last_error ? (
            <div className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-[12px] leading-relaxed text-destructive">
              {sqs.last_error.includes("sqs:receivemessage")
                ? "IAM blocked SQS ReceiveMessage. Attach the CloudCareExecutionQueueWorkerAccess policy below to the API identity."
                : sqs.last_error}
            </div>
          ) : null}
        </Panel>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <Panel title="Setup sequence" eyebrow="Checklist" subtitle="Follow this order so identity, email, cloud access, and execution controls line up." delay={80}>
          <div className="space-y-3">
            {setupSteps.map((step, index) => (
              <div key={step.title} className="rounded-md border border-border bg-background p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="num text-[11px] text-ink-faint">{String(index + 1).padStart(2, "0")}</span>
                    <h3 className="text-[14px] font-semibold text-foreground">{step.title}</h3>
                  </div>
                  <div className="flex gap-1.5">
                    <Badge variant={step.status === "Required" ? "secondary" : "outline"}>{step.status}</Badge>
                    <Badge variant="outline">{step.owner}</Badge>
                  </div>
                </div>
                <p className="mt-2 text-[12.5px] leading-relaxed text-ink-dim">{step.detail}</p>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Required environment" eyebrow="Configuration" subtitle="Backend values live in the monorepo .env; frontend values live in apps/frontend/.env.local." delay={120}>
          <div className="mb-4 grid gap-2 sm:grid-cols-2">
            {envRows.map(([key, value]) => (
              <div key={key} className="rounded-md border border-border bg-background px-3 py-2.5">
                <div className="num text-[11px] font-semibold text-foreground">{key}</div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-ink-faint">{value}</p>
              </div>
            ))}
          </div>
          <CodeBlock>{envSnippet}</CodeBlock>
        </Panel>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-3">
        <MiniCard icon={KeyRound} title="CloudCare account email">
          Use the real account email during registration or SSO linking. Agent command analysis emails are sent to that stored user email, with tenant fallback only when the user record is missing an email.
        </MiniCard>
        <MiniCard icon={MailCheck} title="Brevo authorization">
          Verify the sender under Senders, Domains, IPs. In Security, authorize the server public IP. For this machine the blocked IP was 115.112.9.139.
        </MiniCard>
        <MiniCard icon={Tags} title="Resource tagging">
          Add <span className="num">cloudcare:managed=true</span> only to resources CloudCare may mutate. Keep owner, team, environment, and max-risk tags accurate for scoring and attribution.
        </MiniCard>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <Panel title="Executor trust policy" eyebrow="AWS IAM" subtitle="Attach this to CloudCareExecutorRole and align AWS_EXTERNAL_ID exactly." delay={160}>
          <CodeBlock>{trustPolicy}</CodeBlock>
        </Panel>
        <Panel title="Executor permission policy" eyebrow="AWS IAM" subtitle="Narrow write permissions for the current executor actions." delay={200}>
          <CodeBlock>{awsPolicy}</CodeBlock>
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="SQS execution queue" eyebrow="Async worker" subtitle="Production-style approval to execution flow with retries and a visible queue status endpoint." delay={220}>
          <div className="grid gap-3 lg:grid-cols-3">
            <MiniCard icon={PlayCircle} title="Approval path">
              Approval stores the human decision, sends one SQS message, records the queue message id, and marks the proposal queued_for_execution.
            </MiniCard>
            <MiniCard icon={Terminal} title="Worker path">
              The API starts a background worker when SQS is enabled. The worker long-polls SQS and keeps unexpected failed jobs available for retry.
            </MiniCard>
            <MiniCard icon={ClipboardCheck} title="Status path">
              Use <span className="num">GET /v1/sqs/status</span> to confirm enabled, queue URL configured, worker running, last poll, and processed count.
            </MiniCard>
          </div>
          <div className="mt-4">
            <CodeBlock>{sqsPolicy}</CodeBlock>
          </div>
        </Panel>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel title="Operating policies" eyebrow="Controls" subtitle="Policies CloudCare enforces or reports during the agent pipeline." delay={240}>
          <div className="grid gap-3">
            {policies.map((policy) => (
              <div key={policy.title} className="rounded-md border border-border bg-background p-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="size-4 text-mint" />
                  <h3 className="text-[13.5px] font-semibold text-foreground">{policy.title}</h3>
                </div>
                <p className="mt-2 text-[12.5px] leading-relaxed text-ink-dim">{policy.text}</p>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Go-live verification" eyebrow="Acceptance" subtitle="Use these checks before turning EXECUTION_MODE to live." delay={280}>
          <div className="space-y-3">
            {checks.map(([title, detail]) => (
              <div key={title} className="flex gap-3 rounded-md border border-border bg-background p-4">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />
                <div>
                  <h3 className="text-[13.5px] font-semibold text-foreground">{title}</h3>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-ink-dim">{detail}</p>
                </div>
              </div>
            ))}
            <div className="flex gap-3 rounded-md border border-destructive/30 bg-destructive/10 p-4">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
              <div>
                <h3 className="text-[13.5px] font-semibold text-foreground">Do not enable live mode from a failing baseline</h3>
                <p className="mt-1 text-[12.5px] leading-relaxed text-ink-dim">
                  Resolve email receipts, AWS role assumption, MongoDB persistence, and proposal approval behavior before setting EXECUTION_ENABLED=true.
                </p>
              </div>
            </div>
          </div>
        </Panel>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-3">
        <MiniCard icon={Cloud} title="Collector evidence">
          Monitor writes resources, metrics, FOCUS data, and cloud snapshots. Analyzer findings should always point back to observed data or explicit degraded-mode issues.
        </MiniCard>
        <MiniCard icon={ClipboardCheck} title="Approval evidence">
          Supervisor review records include policy outcome, reason codes, confidence, risk, cost breakdown, and approval-token path.
        </MiniCard>
        <MiniCard icon={PlayCircle} title="Execution evidence">
          Executor records before state, after state, mode, reason codes, actual AWS call flag, rollback descriptor, and completion email receipt path.
        </MiniCard>
      </div>

      <div className="mt-5">
        <Panel title="Local verification commands" eyebrow="Engineer handoff" subtitle="Useful commands for checking a fresh workstation or demo setup." delay={320}>
          <CodeBlock>{`pytest tests/unit/test_agent_command_email.py -q
npx tsc --noEmit
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8007/health
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8007/v1/sqs/status -Headers @{Authorization="Bearer <token>"}
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8007/v1/agent-command/run?provider=aws" -Headers @{Authorization="Bearer <token>"}`}</CodeBlock>
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Live-mode switch" eyebrow="Final gate" subtitle="Use only after the verification checklist is green." delay={360}>
          <CodeBlock>{`EXECUTION_ENABLED=true
EXECUTION_MODE=live
AWS_WRITE_ROLE_ARN=arn:aws:iam::<account-id>:role/CloudCareExecutorRole
EXECUTION_ALLOWLIST_TAG=cloudcare:managed=true`}</CodeBlock>
        </Panel>
      </div>
    </div>
  );
}
