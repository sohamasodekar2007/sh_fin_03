import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  BriefcaseBusiness,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  Gauge,
  LineChart,
  PieChart,
  Radar,
  ShieldCheck,
  Target,
  TrendingUp,
  UsersRound,
  WalletCards,
} from "lucide-react";

import { MarketingFooter, MarketingNav } from "@/components/marketing/SolutionPage";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "Executive Command Center | CloudCare",
  description:
    "CloudCare executive command center for CFOs, founders, and engineering leaders to manage cloud spend, forecasts, unit economics, savings proposals, and approval-ready actions.",
};

const commandMetrics = [
  { label: "Month-to-date cloud spend", value: "$128.6K", detail: "+11.8% vs plan", tone: "text-ember" },
  { label: "Forecasted month-end", value: "$187.4K", detail: "$21.9K avoidable", tone: "text-destructive" },
  { label: "Approved savings pipeline", value: "$42.8K", detail: "31 proposals ready", tone: "text-mint" },
  { label: "Runway impact", value: "+4.2 mo", detail: "after execution", tone: "text-signal" },
];

const leadershipViews = [
  {
    icon: WalletCards,
    title: "CFO spend velocity",
    signal: "Daily burn, forecast drift, budget pressure, and month-end exposure are summarized in one board.",
    decision: "Where are we above plan, and which savings actions protect runway this month?",
    owner: "Finance",
  },
  {
    icon: UsersRound,
    title: "Engineering accountability",
    signal: "Resources are mapped to owners, services, environments, tags, and utilization windows.",
    decision: "Which team owns the waste, what is safe to change, and what needs approval?",
    owner: "Engineering",
  },
  {
    icon: ShieldCheck,
    title: "Operations control",
    signal: "Policy verdicts, approval tokens, blocked actions, and execution records stay visible.",
    decision: "Can the change move now, or should it wait for risk review?",
    owner: "Ops",
  },
  {
    icon: BriefcaseBusiness,
    title: "Founder view",
    signal: "Cloud cost is tied to margin, unit economics, savings progress, and business impact.",
    decision: "How much avoidable infrastructure spend is slowing growth?",
    owner: "Leadership",
  },
];

const forecastRows = [
  { segment: "Compute", actual: "$54.2K", forecast: "$77.8K", risk: "High", action: "$13.4K savings queued" },
  { segment: "Databases", actual: "$31.7K", forecast: "$45.1K", risk: "Medium", action: "$9.7K right-size review" },
  { segment: "Storage", actual: "$22.4K", forecast: "$30.8K", risk: "Medium", action: "$11.3K lifecycle moves" },
  { segment: "Serverless and edge", actual: "$20.3K", forecast: "$33.7K", risk: "Watch", action: "$8.4K tuning plan" },
];

const proposalPipeline = [
  { proposal: "Stop idle non-production EC2 fleet", owner: "Platform", stage: "Approved", savings: "$5.8K/mo" },
  { proposal: "Resize analytics RDS replica", owner: "Data", stage: "CFO review", savings: "$4.6K/mo" },
  { proposal: "Move logs bucket to colder tier", owner: "Security", stage: "Ready", savings: "$3.9K/mo" },
  { proposal: "Tune DynamoDB read capacity", owner: "Payments", stage: "Risk check", savings: "$2.7K/mo" },
  { proposal: "Reduce CDN origin calls", owner: "Growth", stage: "Ready", savings: "$2.1K/mo" },
];

const unitEconomics = [
  { label: "Cloud cost per active customer", value: "$0.84", change: "-18% target after savings" },
  { label: "Infra cost per transaction", value: "$0.0038", change: "Payments team owner mapped" },
  { label: "Gross margin exposure", value: "3.6 pts", change: "recoverable from approved actions" },
  { label: "Engineering queue value", value: "$42.8K", change: "ranked by risk and effort" },
];

const operatingRhythm = [
  {
    step: "Watch",
    body: "Spend velocity, account drift, service growth, and resource utilization are refreshed into a leadership-ready view.",
  },
  {
    step: "Explain",
    body: "CloudCare connects each cost movement to service family, owner, resource evidence, and business impact.",
  },
  {
    step: "Decide",
    body: "Executives see what can be approved, what needs engineering review, and what is blocked by governance.",
  },
  {
    step: "Track",
    body: "Savings move from proposed to approved to executed to verified, with forecast impact visible at every stage.",
  },
];

const executiveQuestions = [
  "What will cloud spend be at month end if we do nothing?",
  "Which approved actions protect runway fastest?",
  "Which teams own the largest avoidable spend?",
  "What savings are blocked by risk, missing tags, or approval?",
];

export default function ExecutiveCommandCenterPage() {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_14%_6%,color-mix(in_oklab,var(--signal)_16%,transparent),transparent_28%),radial-gradient(circle_at_86%_8%,color-mix(in_oklab,var(--mint)_13%,transparent),transparent_24%),radial-gradient(circle_at_50%_0%,color-mix(in_oklab,var(--ember)_10%,transparent),transparent_22%),var(--background)]">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <MarketingNav />
        <main>
          <section className="grid gap-7 py-10 lg:grid-cols-[1.03fr_0.97fr] lg:items-center lg:py-16">
            <div className="stage">
              <div className="eyebrow flex items-center gap-2">
                <Gauge className="size-3.5" />
                Executive cloud command center
              </div>
              <h1 className="mt-5 max-w-4xl text-[clamp(2.4rem,5.9vw,5.15rem)] font-bold leading-[0.97] text-foreground">
                One live control room for cloud spend, savings decisions, and runway impact.
              </h1>
              <p className="mt-6 max-w-2xl text-base font-semibold leading-7 text-signal">
                CloudCare gives CFOs, founders, and engineering leaders the same operating picture: forecast exposure, unit economics, proposal pipeline, governance status, and verified savings.
              </p>
              <p className="mt-4 max-w-2xl text-[13.5px] leading-relaxed text-ink-faint">
                This page is designed for leadership decisions, not passive reporting. It shows what is happening now, what will happen by month end, which actions are ready, who owns them, and how much business impact is recoverable.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href="/dashboard">
                    Open dashboard <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/dashboard/proposals">Review proposals</Link>
                </Button>
              </div>
            </div>

            <div className="stage rounded-xl border border-border bg-surface/90 p-4 shadow-[0_28px_90px_color-mix(in_oklab,var(--foreground)_14%,transparent)]" style={{ animationDelay: "140ms" }}>
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-start justify-between border-b border-background/15 pb-4">
                  <div>
                    <p className="eyebrow text-background/60">Boardroom signal</p>
                    <p className="num mt-3 text-5xl font-bold">$21.9K</p>
                    <p className="mt-1 text-[12px] text-background/70">avoidable month-end exposure detected</p>
                  </div>
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-background/10 text-mint">
                    <LineChart className="size-6" />
                  </span>
                </div>
                <div className="mt-4 grid gap-2">
                  {commandMetrics.map((metric) => (
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

          <section className="grid gap-3 py-6 md:grid-cols-2 lg:grid-cols-4">
            {unitEconomics.map((item, index) => (
              <div key={item.label} className="stage panel p-4" style={{ animationDelay: `${180 + index * 55}ms` }}>
                <CircleDollarSign className="size-4 text-signal" />
                <p className="num mt-4 text-2xl font-bold text-foreground">{item.value}</p>
                <p className="mt-1 text-[12px] font-semibold text-foreground">{item.label}</p>
                <p className="mt-2 text-[11.5px] leading-5 text-ink-faint">{item.change}</p>
              </div>
            ))}
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[0.86fr_1.14fr]">
            <div className="panel overflow-hidden p-6">
              <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--signal),var(--mint),var(--ember))]" />
              <div className="eyebrow flex items-center gap-2">
                <Radar className="size-3.5" />
                Leadership operating layer
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                The command center turns cloud cost into a leadership decision system.
              </h2>
              <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                Finance sees forecast risk. Engineering sees resource ownership. Operations sees approval and policy status. Leadership sees the business result.
              </p>
            </div>
            <div className="grid gap-4">
              {leadershipViews.map((view) => {
                const Icon = view.icon;
                return (
                  <article key={view.title} className="panel grid gap-4 p-5 lg:grid-cols-[0.72fr_1fr_1fr_0.42fr]">
                    <div className="flex gap-3">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent text-signal">
                        <Icon className="size-4.5" />
                      </span>
                      <h3 className="text-base font-semibold text-foreground">{view.title}</h3>
                    </div>
                    <p className="text-[12.5px] leading-6 text-ink-faint">{view.signal}</p>
                    <p className="text-[12.5px] leading-6 text-ink-dim">{view.decision}</p>
                    <p className="num text-left text-sm font-bold text-signal lg:text-right">{view.owner}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="py-8">
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="eyebrow flex items-center gap-2">
                  <TrendingUp className="size-3.5" />
                  Forecast exposure
                </div>
                <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                  See the month-end risk and the savings action in the same row.
                </h2>
              </div>
              <div className="rounded-full border border-border bg-surface px-4 py-2">
                <span className="num text-sm font-semibold text-signal">$187.4K forecasted month-end</span>
              </div>
            </div>
            <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
              <div className="hidden grid-cols-[0.75fr_0.55fr_0.65fr_0.45fr_1fr] bg-foreground px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.04em] text-background/75 lg:grid">
                <span>Segment</span>
                <span>MTD</span>
                <span>Forecast</span>
                <span>Risk</span>
                <span>Action</span>
              </div>
              {forecastRows.map((row) => (
                <div key={row.segment} className="grid gap-3 border-t border-border px-5 py-5 lg:grid-cols-[0.75fr_0.55fr_0.65fr_0.45fr_1fr]">
                  <p className="text-sm font-semibold text-foreground">{row.segment}</p>
                  <p className="num text-sm text-ink-faint">{row.actual}</p>
                  <p className="num text-sm font-bold text-foreground">{row.forecast}</p>
                  <p className={row.risk === "High" ? "text-[12px] font-semibold text-destructive" : "text-[12px] font-semibold text-ember"}>
                    {row.risk}
                  </p>
                  <p className="text-[12.5px] font-medium leading-6 text-signal">{row.action}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[1.06fr_0.94fr]">
            <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                  <div className="eyebrow flex items-center gap-2">
                    <Target className="size-3.5" />
                    Proposal pipeline
                  </div>
                  <h2 className="mt-2 text-2xl font-bold text-foreground">Savings decisions ready for leadership review.</h2>
                </div>
                <Clock3 className="size-5 text-ember" />
              </div>
              {proposalPipeline.map((proposal) => (
                <div key={proposal.proposal} className="grid gap-3 border-b border-border px-5 py-4 last:border-b-0 md:grid-cols-[1.05fr_0.52fr_0.5fr_0.45fr]">
                  <p className="text-sm font-semibold text-foreground">{proposal.proposal}</p>
                  <p className="text-[12px] text-ink-faint">{proposal.owner}</p>
                  <p className="text-[12px] font-semibold text-ember">{proposal.stage}</p>
                  <p className="num text-sm font-bold text-signal md:text-right">{proposal.savings}</p>
                </div>
              ))}
            </div>

            <div className="grid gap-3">
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-center gap-2 text-background/65">
                  <PieChart className="size-4" />
                  <span className="eyebrow text-background/60">Decision focus</span>
                </div>
                <p className="mt-4 text-2xl font-bold leading-tight">
                  The executive page makes the next best cost decision visible without asking leaders to read raw cloud exports.
                </p>
              </div>
              {executiveQuestions.map((question) => (
                <div key={question} className="flex gap-3 rounded-lg border border-border bg-surface p-4">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />
                  <p className="text-[13px] font-medium leading-6 text-foreground">{question}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="panel p-6">
              <div className="eyebrow flex items-center gap-2">
                <BarChart3 className="size-3.5" />
                Operating rhythm
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                From daily cost movement to approved executive action.
              </h2>
              <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                CloudCare makes cloud spend review a repeatable operating meeting: forecast, explain, decide, approve, and verify.
              </p>
            </div>
            <div className="grid gap-3">
              {operatingRhythm.map((item, index) => (
                <div key={item.step} className="rounded-lg border border-border bg-surface p-4">
                  <div className="flex items-center gap-3">
                    <span className="num flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-[12px] text-background">
                      {index + 1}
                    </span>
                    <h3 className="text-sm font-semibold text-foreground">{item.step}</h3>
                  </div>
                  <p className="mt-3 pl-11 text-[12.5px] leading-6 text-ink-faint">{item.body}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="py-8">
            <div className="rounded-lg border border-border bg-foreground p-6 text-background md:flex md:items-center md:justify-between md:gap-8">
              <div>
                <div className="eyebrow text-background/60">Executive outcome</div>
                <h2 className="mt-3 text-3xl font-bold leading-tight">
                  Make every cloud cost review end with a ranked decision, not another spreadsheet.
                </h2>
              </div>
              <Button asChild className="mt-5 shrink-0 md:mt-0" variant="secondary">
                <Link href="/dashboard">
                  Enter command center <ArrowRight className="size-4" />
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
