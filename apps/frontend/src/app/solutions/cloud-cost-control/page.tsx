import Link from "next/link";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock3,
  CloudCog,
  Database,
  Gauge,
  HardDrive,
  LineChart,
  Server,
  TrendingDown,
  Zap,
} from "lucide-react";

import { MarketingFooter, MarketingNav } from "@/components/marketing/SolutionPage";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "Real-Time Cloud Cost Control | CloudCare",
  description:
    "CloudCare real-time cloud cost control for live utilization signals, resource-level waste findings, savings actions, and approval-gated execution.",
};

const liveSignals = [
  { label: "Month-to-date spend", value: "$128.6K", delta: "+11.8% vs plan", tone: "text-ember" },
  { label: "Projected month-end", value: "$187.4K", delta: "$21.9K avoidable", tone: "text-destructive" },
  { label: "Savings ready", value: "$42.8K", delta: "31 actions queued", tone: "text-mint" },
  { label: "Production risk", value: "Low", delta: "24 safe, 7 need approval", tone: "text-signal" },
];

const serviceFindings = [
  {
    icon: Server,
    service: "EC2 and Auto Scaling",
    realtime: "14 instances below 8% CPU for 96 hours, 3 ASGs carrying unused warm capacity",
    recommendation: "Stop non-production nodes, resize two m6i families, and schedule dev capacity outside business hours.",
    impact: "$13.4K/mo",
    confidence: "92%",
  },
  {
    icon: Database,
    service: "RDS and database storage",
    realtime: "4 databases over-provisioned by memory, storage growing faster than read/write pressure",
    recommendation: "Move two instances down one class, review backup retention, and hold production DB changes for approval.",
    impact: "$9.7K/mo",
    confidence: "84%",
  },
  {
    icon: HardDrive,
    service: "EBS, snapshots, and S3",
    realtime: "28 unattached volumes, 116 stale snapshots, 19 TB eligible for colder S3 classes",
    recommendation: "Delete orphaned volumes after owner check, expire stale snapshots, and shift archival objects to IA/Glacier tiers.",
    impact: "$11.3K/mo",
    confidence: "89%",
  },
  {
    icon: Zap,
    service: "Lambda, DynamoDB, CloudFront",
    realtime: "Provisioned throughput mismatch, elevated request cost, and cache behavior creating avoidable origin calls",
    recommendation: "Tune provisioned capacity, adjust cache TTLs, and review traffic spikes before edge configuration changes.",
    impact: "$8.4K/mo",
    confidence: "78%",
  },
];

const realtimeFlow = [
  {
    title: "Live usage ingestion",
    body: "CloudCare reads fresh inventory, cost, CloudWatch-style metrics, tags, and account context so recommendations are based on current behavior instead of old billing exports.",
  },
  {
    title: "Utilization-backed scoring",
    body: "Every finding is ranked by utilization pattern, spend size, recurrence window, owner tag quality, service dependency, and confidence.",
  },
  {
    title: "Approval-ready action",
    body: "The page does not stop at advice. It prepares the action, explains expected savings, marks risk, and routes anything sensitive through human approval.",
  },
];

const approvalQueue = [
  { action: "Stop idle dev EC2 fleet", owner: "Platform", risk: "Low", savings: "$5.8K" },
  { action: "Resize analytics RDS replica", owner: "Data", risk: "Medium", savings: "$4.6K" },
  { action: "Move logs bucket to colder tier", owner: "Security", risk: "Low", savings: "$3.9K" },
  { action: "Reduce DynamoDB provisioned read units", owner: "Payments", risk: "Review", savings: "$2.7K" },
];

export default function CloudCostControlPage() {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_16%_6%,color-mix(in_oklab,var(--mint)_16%,transparent),transparent_30%),radial-gradient(circle_at_82%_0%,color-mix(in_oklab,var(--ember)_17%,transparent),transparent_25%),var(--background)]">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <MarketingNav />
        <main>
          <section className="grid gap-7 py-10 lg:grid-cols-[1.02fr_0.98fr] lg:items-center lg:py-16">
            <div className="stage">
              <div className="eyebrow flex items-center gap-2">
                <Activity className="size-3.5" />
                Real-time cloud cost control
              </div>
              <h1 className="mt-5 max-w-4xl text-[clamp(2.4rem,5.9vw,5.15rem)] font-bold leading-[0.97] text-foreground">
                Stop cloud waste while it is happening, not after the AWS bill arrives.
              </h1>
              <p className="mt-6 max-w-2xl text-base font-semibold leading-7 text-signal">
                CloudCare turns live utilization and spend movement into exact savings actions for compute, databases, storage, serverless, and edge traffic.
              </p>
              <p className="mt-4 max-w-2xl text-[13.5px] leading-relaxed text-ink-faint">
                The cost-control page is built around the real operating question: which resources are wasting money right now, how much can be saved, what is the risk, who owns the decision, and what action is safe to approve.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href="/onboarding">
                    Connect live account <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/cloudcare-vs-aws-billing">Why not only AWS Billing</Link>
                </Button>
              </div>
            </div>

            <div className="stage rounded-xl border border-border bg-surface/90 p-4 shadow-[0_28px_90px_color-mix(in_oklab,var(--foreground)_14%,transparent)]" style={{ animationDelay: "140ms" }}>
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-start justify-between border-b border-background/15 pb-4">
                  <div>
                    <p className="eyebrow text-background/60">Live savings cockpit</p>
                    <p className="num mt-3 text-5xl font-bold">$42.8K</p>
                    <p className="mt-1 text-[12px] text-background/70">monthly savings ready for approval</p>
                  </div>
                  <span className="flex h-12 w-12 items-center justify-center rounded-md bg-background/10 text-mint">
                    <TrendingDown className="size-6" />
                  </span>
                </div>
                <div className="mt-4 grid gap-2">
                  {liveSignals.map((signal) => (
                    <div key={signal.label} className="grid grid-cols-[1fr_auto] gap-3 rounded-md border border-background/15 bg-background/5 px-3 py-2.5">
                      <div>
                        <p className="text-[12px] text-background/75">{signal.label}</p>
                        <p className={`mt-1 text-[11px] font-semibold ${signal.tone}`}>{signal.delta}</p>
                      </div>
                      <p className="num text-lg font-bold">{signal.value}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-5 py-7 lg:grid-cols-[0.86fr_1.14fr]">
            <div className="panel overflow-hidden p-6">
              <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--signal),var(--mint),var(--ember))]" />
              <div className="eyebrow flex items-center gap-2">
                <LineChart className="size-3.5" />
                Why this page is different
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                It is not a static landing page. It explains a live cost-control workflow.
              </h2>
            </div>
            <div className="grid gap-3">
              <p className="rounded-lg border border-border bg-surface p-5 text-[13.5px] leading-7 text-ink-dim">
                AWS Billing shows reliable historical charges, but it usually tells the team about waste after money is already spent. CloudCare watches usage and cost movement continuously, then converts that signal into resource-level actions before the waste becomes permanent.
              </p>
              <p className="rounded-lg border border-border bg-surface p-5 text-[13.5px] leading-7 text-ink-dim">
                For each finding, CloudCare stores the utilization window, the affected resource family, projected savings, owner context, confidence score, and execution policy. That is why the page talks about actions, not only charts.
              </p>
            </div>
          </section>

          <section className="py-8">
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="eyebrow">Live service findings</div>
                <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                  Every cost number is tied to a real-time signal and a recommended action.
                </h2>
              </div>
              <div className="rounded-full border border-border bg-surface px-4 py-2">
                <span className="num text-sm font-semibold text-signal">31 active recommendations</span>
              </div>
            </div>
            <div className="grid gap-4">
              {serviceFindings.map((finding) => {
                const Icon = finding.icon;
                return (
                  <article key={finding.service} className="panel grid gap-4 p-5 lg:grid-cols-[0.75fr_1fr_1fr_0.45fr]">
                    <div className="flex gap-3">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent text-signal">
                        <Icon className="size-4.5" />
                      </span>
                      <div>
                        <h3 className="text-base font-semibold text-foreground">{finding.service}</h3>
                        <p className="num mt-1 text-[11px] text-mint">{finding.confidence} confidence</p>
                      </div>
                    </div>
                    <p className="text-[12.5px] leading-6 text-ink-faint">{finding.realtime}</p>
                    <p className="text-[12.5px] leading-6 text-ink-dim">{finding.recommendation}</p>
                    <p className="num text-left text-xl font-bold text-signal lg:text-right">{finding.impact}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="panel p-6">
              <div className="eyebrow flex items-center gap-2">
                <CloudCog className="size-3.5" />
                Real-time operating flow
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                The workflow follows the data, not a generic template.
              </h2>
              <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                CloudCare starts with fresh telemetry, proves the savings opportunity, checks production risk, then creates a clean approval queue for the team.
              </p>
            </div>
            <div className="grid gap-3">
              {realtimeFlow.map((item, index) => (
                <div key={item.title} className="rounded-lg border border-border bg-surface p-4">
                  <div className="flex items-center gap-3">
                    <span className="num flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-[12px] text-background">
                      {index + 1}
                    </span>
                    <h3 className="text-sm font-semibold text-foreground">{item.title}</h3>
                  </div>
                  <p className="mt-3 pl-11 text-[12.5px] leading-6 text-ink-faint">{item.body}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="py-8">
            <div className="grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
              <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
                <div className="flex items-center justify-between border-b border-border px-5 py-4">
                  <div>
                    <div className="eyebrow">Approval queue</div>
                    <h2 className="mt-2 text-2xl font-bold text-foreground">Savings that are ready to move</h2>
                  </div>
                  <Clock3 className="size-5 text-ember" />
                </div>
                {approvalQueue.map((item) => (
                  <div key={item.action} className="grid gap-3 border-b border-border px-5 py-4 last:border-b-0 md:grid-cols-[1.1fr_0.55fr_0.5fr_0.4fr]">
                    <p className="text-sm font-semibold text-foreground">{item.action}</p>
                    <p className="text-[12px] text-ink-faint">{item.owner}</p>
                    <p className="text-[12px] font-semibold text-ember">{item.risk}</p>
                    <p className="num text-sm font-bold text-signal md:text-right">{item.savings}</p>
                  </div>
                ))}
              </div>

              <div className="grid gap-3">
                {[
                  "Finance sees the avoidable money before month end.",
                  "Engineering sees the exact resource, utilization pattern, and owner.",
                  "Operations gets approval gates, audit trail, and production-risk context.",
                ].map((item) => (
                  <div key={item} className="flex gap-3 rounded-lg border border-border bg-surface p-4">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />
                    <p className="text-[13px] font-medium leading-6 text-foreground">{item}</p>
                  </div>
                ))}
                <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                  <div className="flex items-center gap-2 text-background/65">
                    <Gauge className="size-4" />
                    <span className="eyebrow text-background/60">Result</span>
                  </div>
                  <p className="mt-4 text-2xl font-bold leading-tight">
                    A cost-control page that behaves like a command center: live signals, ranked findings, and approval-ready savings.
                  </p>
                  <Button asChild className="mt-5" variant="secondary">
                    <Link href="/onboarding">
                      Start cost control <ArrowRight className="size-4" />
                    </Link>
                  </Button>
                </div>
              </div>
            </div>
          </section>
        </main>
        <MarketingFooter />
      </div>
    </div>
  );
}
