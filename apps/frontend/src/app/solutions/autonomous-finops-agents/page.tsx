import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Eye,
  FileCheck2,
  Gavel,
  GitBranch,
  Hand,
  LockKeyhole,
  MessageSquareText,
  PlayCircle,
  Radar,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";

import { MarketingFooter, MarketingNav } from "@/components/marketing/SolutionPage";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "Autonomous FinOps Agents | CloudCare",
  description:
    "CloudCare autonomous FinOps agents monitor usage, analyze waste, write proposals, enforce guardrails, and execute approved savings actions.",
};

const agentFleet = [
  {
    icon: Eye,
    name: "Monitor Agent",
    status: "Watching 1,284 resources",
    mission: "Streams inventory, billing movement, utilization metrics, tags, and provider health into one normalized operating view.",
    output: "Fresh resource snapshots",
    latency: "15 min",
  },
  {
    icon: BrainCircuit,
    name: "Analyzer Agent",
    status: "Scoring 86 anomalies",
    mission: "Turns raw telemetry into findings by comparing utilization windows, spend velocity, service type, and historical baselines.",
    output: "Ranked waste findings",
    latency: "Near real-time",
  },
  {
    icon: Sparkles,
    name: "Decision Agent",
    status: "Drafting 31 proposals",
    mission: "Explains the business case in plain language while deterministic rules keep the numbers, risk, and confidence grounded.",
    output: "Approval-ready proposal",
    latency: "On change",
  },
  {
    icon: Gavel,
    name: "Supervisor Agent",
    status: "Guarding production",
    mission: "Checks blast radius, IAM safety, dependency context, owner tags, policy rules, and approval requirements before action.",
    output: "Risk verdict",
    latency: "Before approval",
  },
  {
    icon: Bot,
    name: "Executor Agent",
    status: "Waiting on human approval",
    mission: "Runs only allowlisted, idempotent actions after approval, then records execution evidence and post-action verification.",
    output: "Audited savings action",
    latency: "Approved only",
  },
];

const liveBoard = [
  { label: "Active agents", value: "5", detail: "coordinated roles", tone: "text-signal" },
  { label: "Open findings", value: "86", detail: "fresh signals", tone: "text-ember" },
  { label: "Ready proposals", value: "31", detail: "$42.8K/mo", tone: "text-mint" },
  { label: "Blocked actions", value: "7", detail: "approval needed", tone: "text-destructive" },
];

const timeline = [
  {
    time: "09:12",
    agent: "Monitor",
    event: "Detected three dev ASGs running above scheduled hours with no deployment activity.",
    result: "Opened utilization evidence",
  },
  {
    time: "09:17",
    agent: "Analyzer",
    event: "Matched EC2 spend spike to idle capacity and tagged owner as Platform.",
    result: "$5.8K monthly opportunity",
  },
  {
    time: "09:22",
    agent: "Decision",
    event: "Generated proposal with impact, confidence, dependency notes, and rollback instructions.",
    result: "Ready for review",
  },
  {
    time: "09:24",
    agent: "Supervisor",
    event: "Policy check passed for non-production stop action; database action held for manual review.",
    result: "24 safe, 7 gated",
  },
  {
    time: "09:30",
    agent: "Executor",
    event: "Waiting for signed approval token before any mutating action runs.",
    result: "No unauthorized execution",
  },
];

const controls = [
  {
    icon: Hand,
    title: "Human approval stays in the loop",
    body: "Agents can investigate, score, explain, and prepare. They do not mutate production infrastructure unless the approval path is satisfied.",
  },
  {
    icon: ShieldCheck,
    title: "Policy engine owns execution safety",
    body: "The LLM can write the reasoning, but deterministic checks decide whether an action is allowed, risky, blocked, or approval-gated.",
  },
  {
    icon: FileCheck2,
    title: "Every action has evidence",
    body: "CloudCare stores the finding, metrics window, owner context, approval record, executed command, and verification result.",
  },
];

const commandExamples = [
  "Explain why this RDS resize is safe.",
  "Show all EC2 findings above $2K monthly savings.",
  "Which recommendations are blocked by missing owner tags?",
  "Prepare approval links for low-risk non-production actions.",
];

export default function AutonomousFinopsAgentsPage() {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_12%_8%,color-mix(in_oklab,var(--signal)_18%,transparent),transparent_28%),radial-gradient(circle_at_88%_12%,color-mix(in_oklab,var(--mint)_13%,transparent),transparent_26%),var(--background)]">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <MarketingNav />
        <main>
          <section className="grid gap-7 py-10 lg:grid-cols-[1.02fr_0.98fr] lg:items-center lg:py-16">
            <div className="stage">
              <div className="eyebrow flex items-center gap-2">
                <Radar className="size-3.5" />
                Autonomous FinOps agent system
              </div>
              <h1 className="mt-5 max-w-4xl text-[clamp(2.4rem,5.9vw,5.15rem)] font-bold leading-[0.97] text-foreground">
                Five agents that keep cloud savings moving after the dashboard closes.
              </h1>
              <p className="mt-6 max-w-2xl text-base font-semibold leading-7 text-signal">
                CloudCare does not leave teams with static recommendations. It runs a controlled agent loop that monitors, analyzes, proposes, supervises, and executes only after approval.
              </p>
              <p className="mt-4 max-w-2xl text-[13.5px] leading-relaxed text-ink-faint">
                The agent page is designed like a mission control room. It shows what each agent is doing, what evidence it produces, where human approval is required, and how the system prevents random automation from touching production.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href="/dashboard/agent-command">
                    Open agent command <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/solutions/governance-security">See safety guardrails</Link>
                </Button>
              </div>
            </div>

            <div className="stage rounded-xl border border-border bg-surface/90 p-4 shadow-[0_28px_90px_color-mix(in_oklab,var(--foreground)_14%,transparent)]" style={{ animationDelay: "140ms" }}>
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-start justify-between border-b border-background/15 pb-4">
                  <div>
                    <p className="eyebrow text-background/60">Agent mission board</p>
                    <p className="num mt-3 text-5xl font-bold">5</p>
                    <p className="mt-1 text-[12px] text-background/70">specialized agents in one controlled loop</p>
                  </div>
                  <span className="flex h-12 w-12 items-center justify-center rounded-md bg-background/10 text-mint">
                    <Workflow className="size-6" />
                  </span>
                </div>
                <div className="mt-4 grid gap-2">
                  {liveBoard.map((item) => (
                    <div key={item.label} className="grid grid-cols-[1fr_auto] gap-3 rounded-md border border-background/15 bg-background/5 px-3 py-2.5">
                      <div>
                        <p className="text-[12px] text-background/75">{item.label}</p>
                        <p className={`mt-1 text-[11px] font-semibold ${item.tone}`}>{item.detail}</p>
                      </div>
                      <p className="num text-lg font-bold">{item.value}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="py-8">
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="eyebrow flex items-center gap-2">
                  <GitBranch className="size-3.5" />
                  Agent roles
                </div>
                <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                  Each agent has a separate job, output, and safety boundary.
                </h2>
              </div>
              <div className="rounded-full border border-border bg-surface px-4 py-2">
                <span className="num text-sm font-semibold text-signal">observe to verify</span>
              </div>
            </div>
            <div className="grid gap-4">
              {agentFleet.map((agent, index) => {
                const Icon = agent.icon;
                return (
                  <article
                    key={agent.name}
                    className="stage panel grid gap-4 p-5 lg:grid-cols-[0.75fr_1.1fr_0.55fr_0.42fr]"
                    style={{ animationDelay: `${180 + index * 70}ms` }}
                  >
                    <div className="flex gap-3">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent text-signal">
                        <Icon className="size-4.5" />
                      </span>
                      <div>
                        <h3 className="text-base font-semibold text-foreground">{agent.name}</h3>
                        <p className="mt-1 text-[11px] font-semibold text-mint">{agent.status}</p>
                      </div>
                    </div>
                    <p className="text-[12.5px] leading-6 text-ink-faint">{agent.mission}</p>
                    <p className="text-[12.5px] font-semibold leading-6 text-foreground">{agent.output}</p>
                    <p className="num text-left text-sm font-bold text-signal lg:text-right">{agent.latency}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[0.86fr_1.14fr]">
            <div className="panel overflow-hidden p-6">
              <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--signal),var(--mint),var(--ember))]" />
              <div className="eyebrow flex items-center gap-2">
                <Activity className="size-3.5" />
                Live agent timeline
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                The system shows the chain of reasoning before it asks for approval.
              </h2>
              <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                This is the difference between useful autonomy and risky automation: each handoff produces a visible event, an owner-facing result, and an execution boundary.
              </p>
            </div>
            <div className="grid gap-3">
              {timeline.map((item) => (
                <div key={`${item.time}-${item.agent}`} className="rounded-lg border border-border bg-surface p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="num rounded-full border border-border px-3 py-1 text-[11px] text-signal">{item.time}</span>
                      <h3 className="text-sm font-semibold text-foreground">{item.agent}</h3>
                    </div>
                    <span className="text-[11px] font-semibold text-mint">{item.result}</span>
                  </div>
                  <p className="mt-3 text-[12.5px] leading-6 text-ink-faint">{item.event}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="py-8">
            <div className="grid gap-4 md:grid-cols-3">
              {controls.map((control) => {
                const Icon = control.icon;
                return (
                  <article key={control.title} className="panel p-5">
                    <span className="flex h-10 w-10 items-center justify-center rounded-md bg-accent text-signal">
                      <Icon className="size-4.5" />
                    </span>
                    <h3 className="mt-5 text-xl font-semibold leading-tight text-foreground">{control.title}</h3>
                    <p className="mt-3 text-[12.5px] leading-relaxed text-ink-faint">{control.body}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                  <div className="eyebrow flex items-center gap-2">
                    <MessageSquareText className="size-3.5" />
                    Agent command examples
                  </div>
                  <h2 className="mt-2 text-2xl font-bold text-foreground">Ask operational questions, not generic chatbot prompts.</h2>
                </div>
                <Clock3 className="size-5 text-ember" />
              </div>
              {commandExamples.map((command) => (
                <div key={command} className="flex items-center gap-3 border-b border-border px-5 py-4 last:border-b-0">
                  <PlayCircle className="size-4 shrink-0 text-signal" />
                  <p className="text-sm font-semibold text-foreground">{command}</p>
                </div>
              ))}
            </div>

            <div className="grid gap-3">
              {[
                "Autonomy handles the follow-through that teams usually forget after a cost review.",
                "Deterministic rules hold the authority for execution, so the agent loop remains auditable.",
                "Every proposal can be traced from raw signal to policy verdict to approved action.",
              ].map((item) => (
                <div key={item} className="flex gap-3 rounded-lg border border-border bg-surface p-4">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />
                  <p className="text-[13px] font-medium leading-6 text-foreground">{item}</p>
                </div>
              ))}
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-center gap-2 text-background/65">
                  <LockKeyhole className="size-4" />
                  <span className="eyebrow text-background/60">Control point</span>
                </div>
                <p className="mt-4 text-2xl font-bold leading-tight">
                  Agents can move fast because the system is explicit about where they must stop.
                </p>
                <Button asChild className="mt-5" variant="secondary">
                  <Link href="/dashboard/agent-command">
                    Open command center <ArrowRight className="size-4" />
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
