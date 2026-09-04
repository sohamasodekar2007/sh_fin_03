import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  Fingerprint,
  Gavel,
  GitBranch,
  KeyRound,
  LockKeyhole,
  Radar,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Tag,
} from "lucide-react";

import { MarketingFooter, MarketingNav } from "@/components/marketing/SolutionPage";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "Governance and Security Guardrails | CloudCare",
  description:
    "CloudCare governance and security guardrails for IAM findings, ownership tags, approval tokens, policy checks, dependency context, and audited cloud cost execution.",
};

const controlMetrics = [
  { label: "Unauthorized actions", value: "0", detail: "mutations blocked without approval", tone: "text-mint" },
  { label: "Policy checks", value: "214", detail: "evaluated in the last run", tone: "text-signal" },
  { label: "IAM findings", value: "18", detail: "ranked by exposure", tone: "text-ember" },
  { label: "Missing owners", value: "11", detail: "tag gaps before execution", tone: "text-destructive" },
];

const governanceLayers = [
  {
    icon: KeyRound,
    layer: "IAM exposure review",
    signal: "Wildcard permissions, stale access keys, broad instance profiles, and risky cross-account trust.",
    action: "Rank access risk beside the cost recommendation so savings work does not weaken the account.",
    owner: "Security",
  },
  {
    icon: Tag,
    layer: "Owner and tag governance",
    signal: "Resources without team, environment, cost-center, or application ownership metadata.",
    action: "Hold destructive actions until ownership is clear, then route proposals to the right team.",
    owner: "FinOps",
  },
  {
    icon: GitBranch,
    layer: "Dependency context",
    signal: "Load balancer links, database dependencies, autoscaling membership, snapshots, and production markers.",
    action: "Prevent simple cost rules from shutting down resources that still support an active workflow.",
    owner: "Platform",
  },
  {
    icon: Fingerprint,
    layer: "Approval tokens",
    signal: "Mutating action needs a signed, single-use approval path with expiry and identity context.",
    action: "Execute only after approval, then write the full decision trail into the audit log.",
    owner: "Approver",
  },
];

const policyDecisions = [
  { rule: "Stop idle non-production EC2", verdict: "Allowed", reason: "Owner tag present, no production dependency, rollback path available" },
  { rule: "Resize production RDS", verdict: "Approval", reason: "Savings are high, but database class change needs manual sign-off" },
  { rule: "Delete unattached EBS volume", verdict: "Review", reason: "Volume is unattached but missing owner and snapshot evidence" },
  { rule: "Change public S3 bucket policy", verdict: "Blocked", reason: "Security-sensitive action is outside the cost executor allowlist" },
];

const auditTrail = [
  {
    step: "Finding created",
    detail: "Analyzer identifies a cost action and attaches utilization, spend, service, account, and resource evidence.",
  },
  {
    step: "Governance checked",
    detail: "Policy engine verifies tags, IAM context, dependency risk, environment, allowlist, and approval requirement.",
  },
  {
    step: "Human routed",
    detail: "Supervisor sends approval only to the accountable owner when action risk or policy requires sign-off.",
  },
  {
    step: "Execution recorded",
    detail: "Executor runs the approved action and stores command input, result, timestamp, actor, and verification status.",
  },
];

const guarantees = [
  "Cost savings are never treated as more important than production safety.",
  "The system can explain why an action was allowed, blocked, or sent for approval.",
  "Every recommendation keeps a traceable record from finding to verification.",
];

export default function GovernanceSecurityPage() {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_16%_6%,color-mix(in_oklab,var(--ember)_15%,transparent),transparent_28%),radial-gradient(circle_at_88%_10%,color-mix(in_oklab,var(--signal)_15%,transparent),transparent_28%),var(--background)]">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <MarketingNav />
        <main>
          <section className="grid gap-7 py-10 lg:grid-cols-[1.02fr_0.98fr] lg:items-center lg:py-16">
            <div className="stage">
              <div className="eyebrow flex items-center gap-2">
                <ShieldCheck className="size-3.5" />
                Governance and security guardrails
              </div>
              <h1 className="mt-5 max-w-4xl text-[clamp(2.4rem,5.9vw,5.15rem)] font-bold leading-[0.97] text-foreground">
                Reduce cloud waste without letting automation create production risk.
              </h1>
              <p className="mt-6 max-w-2xl text-base font-semibold leading-7 text-signal">
                CloudCare wraps every savings recommendation with IAM context, ownership checks, policy verdicts, dependency review, approval tokens, and execution audit.
              </p>
              <p className="mt-4 max-w-2xl text-[13.5px] leading-relaxed text-ink-faint">
                This page is built for the real blocker in cloud cost optimization: teams know waste exists, but they do not trust blind automation. CloudCare makes the control path visible so finance can save money and engineering can protect production.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href="/dashboard/governance">
                    Open governance dashboard <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/solutions/autonomous-finops-agents">See agent loop</Link>
                </Button>
              </div>
            </div>

            <div className="stage rounded-xl border border-border bg-surface/90 p-4 shadow-[0_28px_90px_color-mix(in_oklab,var(--foreground)_14%,transparent)]" style={{ animationDelay: "140ms" }}>
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-start justify-between border-b border-background/15 pb-4">
                  <div>
                    <p className="eyebrow text-background/60">Safety control board</p>
                    <p className="num mt-3 text-5xl font-bold">0</p>
                    <p className="mt-1 text-[12px] text-background/70">unauthorized production actions</p>
                  </div>
                  <span className="flex h-12 w-12 items-center justify-center rounded-md bg-background/10 text-mint">
                    <LockKeyhole className="size-6" />
                  </span>
                </div>
                <div className="mt-4 grid gap-2">
                  {controlMetrics.map((metric) => (
                    <div key={metric.label} className="grid grid-cols-[1fr_auto] gap-3 rounded-md border border-background/15 bg-background/5 px-3 py-2.5">
                      <div>
                        <p className="text-[12px] text-background/75">{metric.label}</p>
                        <p className={`mt-1 text-[11px] font-semibold ${metric.tone}`}>{metric.detail}</p>
                      </div>
                      <p className="num text-lg font-bold">{metric.value}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-5 py-7 lg:grid-cols-[0.86fr_1.14fr]">
            <div className="panel overflow-hidden p-6">
              <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--ember),var(--signal),var(--mint))]" />
              <div className="eyebrow flex items-center gap-2">
                <Radar className="size-3.5" />
                Governance intelligence
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                CloudCare checks whether a saving is safe before it asks anyone to approve it.
              </h2>
            </div>
            <div className="grid gap-3">
              <p className="rounded-lg border border-border bg-surface p-5 text-[13.5px] leading-7 text-ink-dim">
                A cost tool that only says “delete this” or “resize that” is not enough for a production environment. CloudCare enriches each recommendation with account, environment, IAM, tag, dependency, and service-risk context before action.
              </p>
              <p className="rounded-lg border border-border bg-surface p-5 text-[13.5px] leading-7 text-ink-dim">
                The result is a governance workflow your team can defend: approved savings move quickly, risky changes pause for review, and unsafe actions are blocked even if the theoretical saving looks attractive.
              </p>
            </div>
          </section>

          <section className="py-8">
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="eyebrow">Control layers</div>
                <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                  Every recommendation passes through security, ownership, dependency, and approval checks.
                </h2>
              </div>
              <div className="rounded-full border border-border bg-surface px-4 py-2">
                <span className="num text-sm font-semibold text-signal">214 checks evaluated</span>
              </div>
            </div>
            <div className="grid gap-4">
              {governanceLayers.map((layer, index) => {
                const Icon = layer.icon;
                return (
                  <article
                    key={layer.layer}
                    className="stage panel grid gap-4 p-5 lg:grid-cols-[0.7fr_1fr_1fr_0.4fr]"
                    style={{ animationDelay: `${170 + index * 70}ms` }}
                  >
                    <div className="flex gap-3">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent text-signal">
                        <Icon className="size-4.5" />
                      </span>
                      <h3 className="text-base font-semibold text-foreground">{layer.layer}</h3>
                    </div>
                    <p className="text-[12.5px] leading-6 text-ink-faint">{layer.signal}</p>
                    <p className="text-[12.5px] leading-6 text-ink-dim">{layer.action}</p>
                    <p className="num text-left text-sm font-bold text-signal lg:text-right">{layer.owner}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[1.06fr_0.94fr]">
            <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                  <div className="eyebrow flex items-center gap-2">
                    <Gavel className="size-3.5" />
                    Policy verdicts
                  </div>
                  <h2 className="mt-2 text-2xl font-bold text-foreground">Same cost goal, different execution decision.</h2>
                </div>
                <ClipboardList className="size-5 text-ember" />
              </div>
              {policyDecisions.map((decision) => (
                <div key={decision.rule} className="grid gap-3 border-b border-border px-5 py-4 last:border-b-0 md:grid-cols-[0.78fr_0.42fr_1fr]">
                  <p className="text-sm font-semibold text-foreground">{decision.rule}</p>
                  <p
                    className={
                      decision.verdict === "Blocked"
                        ? "text-[12px] font-semibold text-destructive"
                        : decision.verdict === "Approval"
                          ? "text-[12px] font-semibold text-ember"
                          : "text-[12px] font-semibold text-mint"
                    }
                  >
                    {decision.verdict}
                  </p>
                  <p className="text-[12px] leading-6 text-ink-faint">{decision.reason}</p>
                </div>
              ))}
            </div>

            <div className="grid gap-3">
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-center gap-2 text-background/65">
                  <ShieldAlert className="size-4" />
                  <span className="eyebrow text-background/60">Risk posture</span>
                </div>
                <p className="mt-4 text-2xl font-bold leading-tight">
                  The system is strongest when it says no to the wrong saving.
                </p>
                <p className="mt-3 text-[12.5px] leading-6 text-background/70">
                  CloudCare is designed to block unsafe mutations, pause ambiguous actions, and move only the recommendations that have enough evidence.
                </p>
              </div>
              {guarantees.map((item) => (
                <div key={item} className="flex gap-3 rounded-lg border border-border bg-surface p-4">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />
                  <p className="text-[13px] font-medium leading-6 text-foreground">{item}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="panel p-6">
              <div className="eyebrow flex items-center gap-2">
                <ScrollText className="size-3.5" />
                Audit trail
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                From finding to execution, every step leaves proof.
              </h2>
              <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                Governance is not just access control. It is the complete decision record that explains why CloudCare acted, waited, or blocked.
              </p>
            </div>
            <div className="grid gap-3">
              {auditTrail.map((item, index) => (
                <div key={item.step} className="rounded-lg border border-border bg-surface p-4">
                  <div className="flex items-center gap-3">
                    <span className="num flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-[12px] text-background">
                      {index + 1}
                    </span>
                    <h3 className="text-sm font-semibold text-foreground">{item.step}</h3>
                  </div>
                  <p className="mt-3 pl-11 text-[12.5px] leading-6 text-ink-faint">{item.detail}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="py-8">
            <div className="rounded-lg border border-border bg-foreground p-6 text-background md:flex md:items-center md:justify-between md:gap-8">
              <div>
                <div className="eyebrow text-background/60">CloudCare governance position</div>
                <h2 className="mt-3 text-3xl font-bold leading-tight">
                  Save money with controls strong enough for production teams.
                </h2>
              </div>
              <Button asChild className="mt-5 shrink-0 md:mt-0" variant="secondary">
                <Link href="/dashboard/governance">
                  Review guardrails <ArrowRight className="size-4" />
                </Link>
              </Button>
            </div>
          </section>
        </main>
        <MarketingFooter />
      </div>
    </div>
  );
}
