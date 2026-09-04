"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Brain,
  Eye,
  Gavel,
  Hand,
  LayoutGrid,
  MessageSquare,
  Play,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { ThemeToggle } from "@/components/cfo/ThemeToggle";
import { Button } from "@/components/ui/button";
import { marketingPages } from "@/components/marketing/landing-pages";
import { useStage } from "@/lib/motion";

const AGENTS = [
  { name: "Monitor", verb: "Observe", icon: Eye, detail: "Pulls inventory, telemetry and billing from every connected account, hourly." },
  { name: "Analyzer", verb: "Detect", icon: Brain, detail: "Deterministic rules flag idle, over-provisioned and unattached resources." },
  { name: "Decision", verb: "Propose", icon: Sparkles, detail: "GPT-4o writes the plain-English case; the deterministic engine sets the numbers." },
  { name: "Supervisor", verb: "Score", icon: Gavel, detail: "Confidence, risk and policy outcome — every proposal, before anyone sees it." },
  { name: "Executor", verb: "Act", icon: Bot, detail: "Idempotent, allowlisted, rollback-ready. Only after a human clicks Approve." },
];

const FEATURES = [
  { icon: LayoutGrid, title: "One normalized ledger", body: "FOCUS 1.0 across AWS, Azure, GCP and VPS — the same columns, the same units, no per-provider special cases." },
  { icon: Gavel, title: "Deterministic policy, always", body: "An LLM may reason and explain. It never decides what executes — that's a rule engine, unit-tested and auditable." },
  { icon: ShieldCheck, title: "A human in the loop", body: "Every mutating action waits on an explicit approval — dashboard click or a signed, single-use email link." },
  { icon: MessageSquare, title: "Ask it directly", body: "A chat interface with real tool calls into your own findings and proposals — never a hallucinated number." },
];

function AgentNode({ agent, index, active }: { agent: (typeof AGENTS)[number]; index: number; active: boolean }) {
  const Icon = agent.icon;
  return (
    <div
      className="stage flex flex-1 flex-col items-center gap-2 text-center"
      style={{ animationDelay: active ? `${360 + index * 120}ms` : undefined, opacity: active ? undefined : 0 }}
    >
      <span
        className="flex h-11 w-11 items-center justify-center rounded-full border"
        style={{ borderColor: "var(--border)", background: "var(--surface-raised)", color: "var(--signal)" }}
      >
        <Icon className="size-5" />
      </span>
      <div className="eyebrow">{agent.verb}</div>
      <div className="text-[13px] font-semibold text-foreground">{agent.name}</div>
      <p className="max-w-[9.5rem] text-[11px] leading-snug text-ink-faint">{agent.detail}</p>
    </div>
  );
}

function PipelineConnector({ index, active, pause }: { index: number; active: boolean; pause?: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-1 pt-5">
      <div className="relative h-px w-full" style={{ background: "var(--hairline)" }}>
        <div
          className="sweep-in absolute inset-0"
          style={{
            background: "var(--signal)",
            animationDelay: active ? `${420 + index * 120}ms` : undefined,
            opacity: active ? undefined : 0,
          }}
        />
      </div>
      {pause && (
        <div
          className="stage mt-2 flex items-center gap-1 rounded-full border px-2 py-0.5"
          style={{ borderColor: "var(--ember-soft)", color: "var(--ember)", animationDelay: active ? "900ms" : undefined, opacity: active ? undefined : 0 }}
        >
          <Hand className="size-3" />
          <span className="text-[9.5px] font-semibold uppercase tracking-[0.05em]">Human approval</span>
        </div>
      )}
    </div>
  );
}

export default function LandingPage() {
  const heroOn = useStage(80);
  const pipelineOn = useStage(260);
  const howOn = useStage(360);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        {/* ================= nav ================= */}
        <header className="stage flex items-center justify-between py-5">
          <Link href="/" className="flex items-center gap-2.5 font-display text-lg font-bold text-foreground">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: "var(--signal)" }} />
            CloudCare
          </Link>
          <nav className="hidden items-center gap-5 lg:flex">
            <Link href="/solutions/cloud-cost-control" className="text-[11.5px] font-medium text-ink-faint hover:text-foreground">
              Solutions
            </Link>
            <Link href="/cloudcare-vs-aws-billing" className="text-[11.5px] font-medium text-ink-faint hover:text-foreground">
              Vs AWS Billing
            </Link>
            <Link href="/dashboard" className="text-[11.5px] font-medium text-ink-faint hover:text-foreground">
              Dashboard
            </Link>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button asChild variant="ghost" size="sm">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/onboarding">Get started</Link>
            </Button>
          </div>
        </header>

        {/* ================= hero ================= */}
        <section className="stage flex flex-col items-start gap-5 py-14 sm:py-20" style={{ animationDelay: "60ms", opacity: heroOn ? undefined : 0 }}>
          <div className="eyebrow">Multi-cloud FinOps</div>
          <h1 className="max-w-2xl text-[clamp(2rem,4.4vw,3.4rem)] font-bold leading-[1.04] text-foreground">
            Cloud waste, found and fixed — with a human always in the loop.
          </h1>
          <p className="max-w-xl text-[13.5px] leading-relaxed text-ink-faint">
            CloudCare watches AWS, Azure, GCP and your own servers, normalizes every dollar into
            one ledger, and proposes exactly what to stop, resize or delete — scored, explained,
            and never executed without your approval.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/onboarding">
                Connect an account <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/login">
                <Play className="size-4" /> Sign in
              </Link>
            </Button>
          </div>
        </section>

        {/* ================= pipeline ================= */}
        <section className="mt-4">
          <Panel
            eyebrow="How a dollar gets saved"
            title="Five agents, one pipeline"
            subtitle="Monitor → Analyzer → Decision → Supervisor → Executor. Nothing mutates without the pause in the middle."
            delay={200}
          >
            <div className="flex flex-col gap-1 sm:flex-row sm:items-start">
              {AGENTS.map((agent, i) => (
                <div key={agent.name} className="flex flex-1 items-start sm:contents">
                  <AgentNode agent={agent} index={i} active={pipelineOn} />
                  {i < AGENTS.length - 1 && (
                    <div className="hidden sm:flex sm:flex-1">
                      <PipelineConnector index={i} active={pipelineOn} pause={i === 3} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Panel>
        </section>

        {/* ================= features ================= */}
        <section className="mt-5 grid gap-5 sm:grid-cols-2">
          {FEATURES.map((f, i) => {
            const Icon = f.icon;
            return (
              <Panel
                key={f.title}
                title={f.title}
                subtitle={f.body}
                delay={280 + i * 60}
                bodyClassName="hidden"
                aside={
                  <span
                    aria-hidden
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md"
                    style={{ background: "var(--accent)", color: "var(--signal)" }}
                  >
                    <Icon className="size-4.5" />
                  </span>
                }
              >
                {null}
              </Panel>
            );
          })}
        </section>

        {/* ================= solution landing pages ================= */}
        <section className="mt-5">
          <Panel
            eyebrow="What we provide"
            title="Five powerful landing pages plus the exact CloudCare vs AWS Billing comparison."
            subtitle="Use these pages to explain why CloudCare is not just another cost chart. It is the FinOps action layer for savings, agents, governance, multi-cloud coverage and executive decisions."
            delay={340}
          >
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {marketingPages.map((page) => (
                <Link
                  key={page.slug}
                  href={`/solutions/${page.slug}`}
                  className="group rounded-lg border border-border bg-surface-raised p-4 transition hover:border-signal/60"
                >
                  <div className="eyebrow">{page.eyebrow}</div>
                  <h3 className="mt-3 min-h-[3.5rem] text-lg font-semibold leading-tight text-foreground">
                    {page.title}
                  </h3>
                  <p className="mt-3 text-[12px] leading-relaxed text-ink-faint">{page.accent}</p>
                  <span className="mt-4 inline-flex items-center gap-2 text-[12px] font-semibold text-signal">
                    Open page <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
                  </span>
                </Link>
              ))}
              <Link
                href="/cloudcare-vs-aws-billing"
                className="group rounded-lg border border-foreground bg-foreground p-4 text-background transition hover:border-signal"
              >
                <div className="eyebrow text-background/55">Comparison</div>
                <h3 className="mt-3 min-h-[3.5rem] text-lg font-semibold leading-tight">
                  CloudCare vs AWS Billing
                </h3>
                <p className="mt-3 text-[12px] leading-relaxed text-background/65">
                  AWS Billing is the bill of record. CloudCare is the AI action layer that helps teams reduce spend.
                </p>
                <span className="mt-4 inline-flex items-center gap-2 text-[12px] font-semibold text-ember">
                  Open comparison <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
                </span>
              </Link>
            </div>
          </Panel>
        </section>

        {/* ================= how it works: FOCUS ================= */}
        <section className="mt-5">
          <Panel
            eyebrow="Under the hood"
            title="One column set, every provider"
            subtitle="FOCUS 1.0 (FinOps Open Cost & Usage Specification) is the normalization layer everything else is built on."
            delay={360}
          >
            <div className="grid gap-5 sm:grid-cols-3">
              <div className="stage" style={{ animationDelay: howOn ? "400ms" : undefined, opacity: howOn ? undefined : 0 }}>
                <div className="eyebrow">1 · Ingest</div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-ink-dim">
                  Real FOCUS 1.0 exports when a provider emits them (Azure natively does); otherwise
                  synthesized from that provider&apos;s own inventory, metrics and cost APIs.
                </p>
              </div>
              <div className="stage" style={{ animationDelay: howOn ? "460ms" : undefined, opacity: howOn ? undefined : 0 }}>
                <div className="eyebrow">2 · Normalize</div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-ink-dim">
                  BilledCost, ServiceCategory, ResourceId, ChargePeriod — the same 40+ columns
                  whether the row came from AWS, Azure, GCP sample data, or a self-hosted VPS.
                </p>
              </div>
              <div className="stage" style={{ animationDelay: howOn ? "520ms" : undefined, opacity: howOn ? undefined : 0 }}>
                <div className="eyebrow">3 · Analyze</div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-ink-dim">
                  One rule engine reads the normalized ledger — idle, over-provisioned, unattached,
                  anomalous — with no per-provider branching logic to keep in sync.
                </p>
              </div>
            </div>
          </Panel>
        </section>

        {/* ================= footer ================= */}
        <footer className="stage mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border/70 py-6">
          <p className="num text-[10.5px] tracking-[0.04em] text-ink-faint">CloudCare · multi-cloud FinOps</p>
          <div className="flex items-center gap-4">
            <Link href="/login" className="text-[11.5px] font-medium text-ink-faint hover:text-foreground">Sign in</Link>
            <Link href="/onboarding" className="text-[11.5px] font-medium text-ink-faint hover:text-foreground">Get started</Link>
          </div>
        </footer>
      </div>
    </div>
  );
}
