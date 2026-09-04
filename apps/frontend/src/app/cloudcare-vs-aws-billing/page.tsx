import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BarChart3,
  Bot,
  CheckCircle2,
  CircleDollarSign,
  ClipboardCheck,
  Clock3,
  Database,
  FileSearch,
  Gauge,
  GitBranch,
  Layers3,
  LockKeyhole,
  ReceiptText,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  Workflow,
  X,
} from "lucide-react";

import { MarketingFooter, MarketingNav } from "@/components/marketing/SolutionPage";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "CloudCare vs AWS Billing | CloudCare",
  description:
    "Advanced comparison of CloudCare and AWS Billing across billing truth, FinOps execution, AI agents, governance, approvals, multi-cloud visibility, and savings workflows.",
};

const executiveStats = [
  { label: "Billing truth", aws: "Strong", cloudcare: "Uses and enriches it" },
  { label: "Savings execution", aws: "Manual", cloudcare: "Agent-assisted" },
  { label: "Approval workflow", aws: "Outside billing", cloudcare: "Built in" },
  { label: "Provider coverage", aws: "AWS only", cloudcare: "AWS, Azure, FOCUS, VPS" },
];

const capabilityMatrix = [
  {
    icon: ReceiptText,
    capability: "Billing record",
    aws: "Excellent source of AWS invoice, charge history, Cost Explorer reports, budgets, and account billing truth.",
    cloudcare: "Keeps billing context, then connects spend to resource evidence, owners, confidence, and operational action.",
    verdict: "AWS Billing for invoice truth; CloudCare for using that truth.",
  },
  {
    icon: TrendingDown,
    capability: "Waste reduction",
    aws: "Shows where money went and may surface native recommendations, but teams still investigate and execute separately.",
    cloudcare: "Identifies idle, oversized, orphaned, anomalous, and policy-sensitive resources with monthly savings impact.",
    verdict: "CloudCare",
  },
  {
    icon: Bot,
    capability: "Autonomous follow-through",
    aws: "Alerts and dashboards require humans to translate data into repeated FinOps work.",
    cloudcare: "Monitor, Analyzer, Decision, Supervisor, and Executor agents keep the savings pipeline moving.",
    verdict: "CloudCare",
  },
  {
    icon: ShieldCheck,
    capability: "Governance and safety",
    aws: "IAM, billing, tags, and service controls exist, but they are spread across AWS services and teams.",
    cloudcare: "Checks IAM exposure, owner tags, dependency context, policy rules, approval tokens, and audit trail in one flow.",
    verdict: "CloudCare",
  },
  {
    icon: Layers3,
    capability: "Multi-cloud and VPS",
    aws: "Built for AWS accounts and AWS billing structures.",
    cloudcare: "Normalizes AWS, Azure, FOCUS-style data, and VPS fleets so leadership sees one cost operating picture.",
    verdict: "CloudCare",
  },
  {
    icon: ClipboardCheck,
    capability: "Decision readiness",
    aws: "Great for finance review and historical reporting.",
    cloudcare: "Built for approval decisions: what to change, why, risk level, owner, savings, and execution status.",
    verdict: "CloudCare",
  },
];

const workflowComparison = [
  {
    stage: "Detect",
    aws: "User opens reports, filters cost dimensions, exports CSV, and searches for a spend spike.",
    cloudcare: "Agents continuously inspect cost, utilization, inventory, tags, and dependency signals.",
  },
  {
    stage: "Explain",
    aws: "Team manually connects billing data to the actual resource and operational owner.",
    cloudcare: "Finding includes resource id, service family, utilization window, owner context, and confidence.",
  },
  {
    stage: "Decide",
    aws: "Recommendation must be discussed in another tool or meeting.",
    cloudcare: "Proposal is already ranked by savings, risk, policy verdict, and approval requirement.",
  },
  {
    stage: "Act",
    aws: "Engineer manually performs the change in AWS after separate validation.",
    cloudcare: "Executor prepares allowlisted actions and runs them only after approval.",
  },
  {
    stage: "Prove",
    aws: "Savings must be checked later from billing trend changes.",
    cloudcare: "Audit record captures before/after evidence, execution status, and verification result.",
  },
];

const useCases = [
  {
    title: "Use AWS Billing when",
    icon: CircleDollarSign,
    points: [
      "You need official AWS invoice data.",
      "Finance wants historical charge reports.",
      "You are setting budgets or reviewing account billing.",
      "You need the native AWS source of truth.",
    ],
  },
  {
    title: "Use CloudCare when",
    icon: Sparkles,
    points: [
      "You need to reduce spend, not only inspect it.",
      "Engineering needs resource-level proof.",
      "Leadership wants a prioritized savings queue.",
      "Actions need safety checks, approval, and audit.",
    ],
  },
];

const advancedSignals = [
  { label: "Live savings pipeline", value: "$42.8K/mo", icon: TrendingDown },
  { label: "Findings with evidence", value: "86 active", icon: FileSearch },
  { label: "Approval-ready actions", value: "31 queued", icon: BadgeCheck },
  { label: "Policy evaluations", value: "214 checked", icon: LockKeyhole },
  { label: "Cloud and VPS scope", value: "4 provider families", icon: Database },
  { label: "Unauthorized actions", value: "0 allowed", icon: ShieldCheck },
];

const verdictCards = [
  {
    title: "AWS Billing is the record.",
    body: "It tells you the official charge, account, service, budget, and invoice history. You should keep it.",
  },
  {
    title: "CloudCare is the operating layer.",
    body: "It turns billing and utilization data into findings, proposals, approvals, actions, and verified savings.",
  },
  {
    title: "The winning setup uses both.",
    body: "AWS Billing answers what was charged. CloudCare answers what should change next and how to do it safely.",
  },
];

export default function CloudCareVsAwsBillingPage() {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_12%_7%,color-mix(in_oklab,var(--signal)_18%,transparent),transparent_28%),radial-gradient(circle_at_86%_4%,color-mix(in_oklab,var(--ember)_18%,transparent),transparent_26%),var(--background)]">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <MarketingNav />
        <main>
          <section className="grid gap-7 py-10 lg:grid-cols-[1.06fr_0.94fr] lg:items-center lg:py-16">
            <div className="stage">
              <div className="eyebrow flex items-center gap-2">
                <ReceiptText className="size-3.5" />
                Advanced comparison
              </div>
              <h1 className="mt-5 max-w-4xl text-[clamp(2.4rem,5.9vw,5.15rem)] font-bold leading-[0.97] text-foreground">
                AWS Billing records the spend. CloudCare turns spend into controlled savings.
              </h1>
              <p className="mt-6 max-w-2xl text-base font-semibold leading-7 text-signal">
                This is not a replacement story. AWS Billing is the billing truth. CloudCare is the AI FinOps action layer that sits above billing, utilization, resources, policies, and approvals.
              </p>
              <p className="mt-4 max-w-2xl text-[13.5px] leading-relaxed text-ink-faint">
                The difference is simple: AWS Billing helps you understand charges after they exist. CloudCare helps you detect waste early, explain the exact resource problem, approve safe changes, and verify the savings after execution.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href="/solutions/cloud-cost-control">
                    See cost control <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/solutions/autonomous-finops-agents">See agent execution</Link>
                </Button>
              </div>
            </div>

            <div className="stage rounded-xl border border-border bg-surface/90 p-4 shadow-[0_28px_90px_color-mix(in_oklab,var(--foreground)_14%,transparent)]" style={{ animationDelay: "140ms" }}>
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-start justify-between border-b border-background/15 pb-4">
                  <div>
                    <p className="eyebrow text-background/60">Executive verdict</p>
                    <p className="mt-3 text-3xl font-bold leading-tight">Billing truth plus FinOps action.</p>
                    <p className="mt-2 text-[12px] leading-6 text-background/70">
                      Keep AWS Billing for official charge history. Add CloudCare when the goal is savings execution.
                    </p>
                  </div>
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-background/10 text-ember">
                    <Workflow className="size-6" />
                  </span>
                </div>
                <div className="mt-4 grid gap-2">
                  {executiveStats.map((item) => (
                    <div key={item.label} className="grid gap-2 rounded-md border border-background/15 bg-background/5 px-3 py-2.5 sm:grid-cols-[0.8fr_0.7fr_0.9fr]">
                      <p className="text-[12px] font-semibold text-background">{item.label}</p>
                      <p className="text-[12px] text-background/62">AWS: {item.aws}</p>
                      <p className="text-[12px] text-mint">CloudCare: {item.cloudcare}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-3 py-6 md:grid-cols-3 lg:grid-cols-6">
            {advancedSignals.map((signal, index) => {
              const Icon = signal.icon;
              return (
                <div key={signal.label} className="stage panel p-4" style={{ animationDelay: `${180 + index * 45}ms` }}>
                  <Icon className="size-4 text-signal" />
                  <p className="num mt-4 text-xl font-bold text-foreground">{signal.value}</p>
                  <p className="mt-1 text-[11.5px] leading-5 text-ink-faint">{signal.label}</p>
                </div>
              );
            })}
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[0.86fr_1.14fr]">
            <div className="panel overflow-hidden p-6">
              <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--signal),var(--ember),var(--mint))]" />
              <div className="eyebrow flex items-center gap-2">
                <Target className="size-3.5" />
                Positioning
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                AWS Billing is necessary. It is not sufficient when the team must act.
              </h2>
            </div>
            <div className="grid gap-3">
              <p className="rounded-lg border border-border bg-surface p-5 text-[13.5px] leading-7 text-ink-dim">
                AWS Billing is excellent for official AWS cost history, budgets, reports, and invoice truth. But it is intentionally centered on billing data, not on a full operational workflow for finding waste, proving safety, asking for approval, executing changes, and verifying savings.
              </p>
              <p className="rounded-lg border border-border bg-surface p-5 text-[13.5px] leading-7 text-ink-dim">
                CloudCare is built for the layer after visibility. It connects spend to utilization, resource inventory, ownership tags, governance policy, agent reasoning, approval tokens, and execution audit so cost optimization becomes a repeatable operating process.
              </p>
            </div>
          </section>

          <section className="py-8">
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="eyebrow">Capability matrix</div>
                <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                  The practical difference across finance, engineering, and operations.
                </h2>
              </div>
              <div className="rounded-full border border-border bg-surface px-4 py-2">
                <span className="num text-sm font-semibold text-signal">CloudCare = action layer</span>
              </div>
            </div>
            <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
              <div className="hidden grid-cols-[0.72fr_1fr_1fr_0.75fr] bg-foreground px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.04em] text-background/75 lg:grid">
                <span>Capability</span>
                <span>AWS Billing</span>
                <span>CloudCare</span>
                <span>Verdict</span>
              </div>
              {capabilityMatrix.map((row) => {
                const Icon = row.icon;
                return (
                  <article key={row.capability} className="grid gap-4 border-t border-border px-5 py-5 lg:grid-cols-[0.72fr_1fr_1fr_0.75fr]">
                    <div className="flex gap-3">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent text-signal">
                        <Icon className="size-4.5" />
                      </span>
                      <h3 className="text-base font-semibold text-foreground">{row.capability}</h3>
                    </div>
                    <div className="flex gap-3">
                      <X className="mt-1 size-4 shrink-0 text-ember" />
                      <p className="text-[12.5px] leading-6 text-ink-faint">{row.aws}</p>
                    </div>
                    <div className="flex gap-3">
                      <BadgeCheck className="mt-1 size-4 shrink-0 text-mint" />
                      <p className="text-[12.5px] font-medium leading-6 text-foreground">{row.cloudcare}</p>
                    </div>
                    <p className="text-[12.5px] font-semibold leading-6 text-signal">{row.verdict}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="panel p-6">
              <div className="eyebrow flex items-center gap-2">
                <GitBranch className="size-3.5" />
                Workflow difference
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                Same cloud bill, completely different operating motion.
              </h2>
              <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                AWS Billing gives the financial record. CloudCare turns the record into an action pipeline owned by agents, policy, and approvals.
              </p>
            </div>
            <div className="grid gap-3">
              {workflowComparison.map((stage, index) => (
                <div key={stage.stage} className="rounded-lg border border-border bg-surface p-4">
                  <div className="flex items-center gap-3">
                    <span className="num flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-[12px] text-background">
                      {index + 1}
                    </span>
                    <h3 className="text-sm font-semibold text-foreground">{stage.stage}</h3>
                  </div>
                  <div className="mt-3 grid gap-3 pl-11 md:grid-cols-2">
                    <p className="rounded-md border border-border bg-surface-raised p-3 text-[12px] leading-6 text-ink-faint">
                      <span className="font-semibold text-ember">AWS Billing: </span>
                      {stage.aws}
                    </p>
                    <p className="rounded-md border border-border bg-surface-raised p-3 text-[12px] leading-6 text-foreground">
                      <span className="font-semibold text-mint">CloudCare: </span>
                      {stage.cloudcare}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-2">
            {useCases.map((useCase) => {
              const Icon = useCase.icon;
              return (
                <article key={useCase.title} className="panel p-6">
                  <div className="flex items-center gap-3">
                    <span className="flex h-10 w-10 items-center justify-center rounded-md bg-accent text-signal">
                      <Icon className="size-4.5" />
                    </span>
                    <h2 className="text-2xl font-bold text-foreground">{useCase.title}</h2>
                  </div>
                  <div className="mt-5 grid gap-3">
                    {useCase.points.map((point) => (
                      <div key={point} className="flex gap-3 rounded-lg border border-border bg-surface-raised p-3">
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />
                        <p className="text-[13px] font-medium leading-6 text-foreground">{point}</p>
                      </div>
                    ))}
                  </div>
                </article>
              );
            })}
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[1.08fr_0.92fr]">
            <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                  <div className="eyebrow flex items-center gap-2">
                    <Gauge className="size-3.5" />
                    Outcome summary
                  </div>
                  <h2 className="mt-2 text-2xl font-bold text-foreground">
                    What changes when CloudCare sits above AWS Billing?
                  </h2>
                </div>
                <Clock3 className="size-5 text-ember" />
              </div>
              {[
                "Finance gets forecasted exposure and approved savings pipeline instead of only historical charge charts.",
                "Engineering gets resource-level evidence, owners, risk, and exact next actions instead of manual investigation.",
                "Operations gets approval-gated execution and audit records instead of disconnected tickets and tribal knowledge.",
                "Leadership gets one cross-provider view of cloud, managed services, and VPS cost movement.",
              ].map((item) => (
                <div key={item} className="flex gap-3 border-b border-border px-5 py-4 last:border-b-0">
                  <BarChart3 className="mt-0.5 size-4 shrink-0 text-signal" />
                  <p className="text-[13px] font-medium leading-6 text-foreground">{item}</p>
                </div>
              ))}
            </div>

            <div className="grid gap-3">
              {verdictCards.map((card, index) => (
                <div key={card.title} className="rounded-lg border border-border bg-surface p-5">
                  <div className="flex items-center gap-3">
                    <span className="num flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-[12px] text-background">
                      {index + 1}
                    </span>
                    <h3 className="text-lg font-semibold text-foreground">{card.title}</h3>
                  </div>
                  <p className="mt-3 pl-11 text-[12.5px] leading-6 text-ink-faint">{card.body}</p>
                </div>
              ))}
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-center gap-2 text-background/65">
                  <AlertTriangle className="size-4" />
                  <span className="eyebrow text-background/60">Bottom line</span>
                </div>
                <p className="mt-4 text-2xl font-bold leading-tight">
                  If the goal is only to know the bill, AWS Billing is enough. If the goal is to win savings, CloudCare is the missing layer.
                </p>
                <Button asChild className="mt-5" variant="secondary">
                  <Link href="/onboarding">
                    Start with CloudCare <ArrowRight className="size-4" />
                  </Link>
                </Button>
              </div>
            </div>
          </section>
        </main>
        <MarketingFooter />
      </div>
    </div>
  );
}
