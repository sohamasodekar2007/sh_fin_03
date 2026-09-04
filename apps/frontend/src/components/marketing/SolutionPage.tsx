import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  CircleDollarSign,
  ClipboardCheck,
  LineChart,
  ShieldCheck,
  TrendingDown,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { MarketingPage, solutionLinks } from "@/components/marketing/landing-pages";

export function MarketingNav() {
  return (
    <header className="stage flex items-center justify-between py-5">
      <Link href="/" className="flex items-center gap-2.5 font-display text-lg font-bold text-foreground">
        <span className="inline-block h-2 w-2 rounded-full bg-signal" />
        CloudCare
      </Link>
      <nav className="hidden items-center gap-5 lg:flex">
        {solutionLinks.slice(0, 5).map((link) => (
          <Link key={link.href} href={link.href} className="text-[11.5px] font-medium text-ink-faint hover:text-foreground">
            {link.label}
          </Link>
        ))}
      </nav>
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost" size="sm">
          <Link href="/login">Sign in</Link>
        </Button>
        <Button asChild size="sm">
          <Link href="/onboarding">Get started</Link>
        </Button>
      </div>
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="stage mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border/70 py-6">
      <p className="num text-[10.5px] tracking-[0.04em] text-ink-faint">CloudCare - multi-cloud FinOps</p>
      <div className="flex flex-wrap items-center gap-4">
        {solutionLinks.map((link) => (
          <Link key={link.href} href={link.href} className="text-[11.5px] font-medium text-ink-faint hover:text-foreground">
            {link.label}
          </Link>
        ))}
      </div>
    </footer>
  );
}

export default function SolutionPage({ page }: { page: MarketingPage }) {
  const isCostControl = page.slug === "cloud-cost-control";

  return (
    <div
      className={
        isCostControl
          ? "min-h-screen bg-[radial-gradient(circle_at_18%_8%,color-mix(in_oklab,var(--signal)_13%,transparent),transparent_28%),radial-gradient(circle_at_78%_0%,color-mix(in_oklab,var(--ember)_15%,transparent),transparent_24%),var(--background)]"
          : "min-h-screen bg-background"
      }
    >
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <MarketingNav />
        <main>
          <section className="grid gap-7 py-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:py-16">
            <div className="stage" style={{ animationDelay: "80ms" }}>
              <div className="eyebrow flex items-center gap-2">
                <CircleDollarSign className="size-3.5" />
                {page.eyebrow}
              </div>
              <h1 className="mt-5 max-w-3xl text-[clamp(2.35rem,5.7vw,5rem)] font-bold leading-[0.98] text-foreground">
                {page.title}
              </h1>
              <p className="mt-6 max-w-2xl text-base font-semibold leading-7 text-signal">{page.accent}</p>
              <p className="mt-4 max-w-2xl text-[13.5px] leading-relaxed text-ink-faint">{page.summary}</p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href="/onboarding">
                    Launch CloudCare <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/cloudcare-vs-aws-billing">Compare with AWS Billing</Link>
                </Button>
              </div>
            </div>

            <div
              className={
                isCostControl
                  ? "stage rounded-xl border border-border bg-surface/90 p-4 shadow-[0_28px_90px_color-mix(in_oklab,var(--foreground)_14%,transparent)]"
                  : "stage panel p-4"
              }
              style={{ animationDelay: "180ms" }}
            >
              <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                <div className="flex items-start justify-between gap-4 border-b border-background/15 pb-4">
                  <div>
                    <p className="eyebrow text-background/60">
                      {isCostControl ? "Monthly waste pipeline" : "Optimization command"}
                    </p>
                    <p className="num mt-3 text-5xl font-bold">{page.metric}</p>
                    <p className="mt-1 text-[12px] text-background/70">{page.metricLabel}</p>
                  </div>
                  <span className="flex h-12 w-12 items-center justify-center rounded-md bg-background/10 text-mint">
                    <ShieldCheck className="size-6" />
                  </span>
                </div>
                <div className="mt-4 grid gap-2">
                  {page.rows.map((row) => (
                    <div key={row.label} className="flex items-center justify-between rounded-md border border-background/15 bg-background/5 px-3 py-2.5">
                      <span className="text-[12px] text-background/75">{row.label}</span>
                      <span className="num text-[12px] font-semibold">{row.value}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                {page.proof.map((item) => (
                  <div key={item.label} className="rounded-md border border-border bg-surface-raised p-3">
                    <p className="eyebrow">{item.label}</p>
                    <p className="mt-2 text-[12px] font-semibold text-foreground">{item.value}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {isCostControl && page.narrative && (
            <section className="grid gap-5 py-7 lg:grid-cols-[0.85fr_1.15fr]">
              <div className="panel overflow-hidden p-6">
                <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--signal),var(--mint),var(--ember))]" />
                <div className="eyebrow flex items-center gap-2">
                  <LineChart className="size-3.5" />
                  Cost intelligence layer
                </div>
                <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                  The page is built around real FinOps work: detect, prove, approve, save.
                </h2>
                <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                  The numbers on this page are grouped by the same categories CloudCare evaluates in the product:
                  compute, databases, storage, serverless, edge, and account-level governance.
                </p>
              </div>
              <div className="grid gap-3">
                {page.narrative.map((paragraph) => (
                  <p key={paragraph} className="rounded-lg border border-border bg-surface p-5 text-[13.5px] leading-7 text-ink-dim">
                    {paragraph}
                  </p>
                ))}
              </div>
            </section>
          )}

          <section className="grid gap-4 py-6 md:grid-cols-3">
            {page.pillars.map((pillar, index) => {
              const Icon = pillar.icon;
              return (
                <article key={pillar.title} className="stage panel p-5" style={{ animationDelay: `${260 + index * 70}ms` }}>
                  <span className="flex h-10 w-10 items-center justify-center rounded-md bg-accent text-signal">
                    <Icon className="size-4.5" />
                  </span>
                  <h2 className="mt-5 text-xl font-semibold leading-tight text-foreground">{pillar.title}</h2>
                  <p className="mt-3 text-[12.5px] leading-relaxed text-ink-faint">{pillar.body}</p>
                </article>
              );
            })}
          </section>

          {isCostControl && page.serviceBreakdown && (
            <section className="py-8">
              <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <div className="eyebrow">Savings by service family</div>
                  <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                    Every saving needs a resource, a reason, and a next action.
                  </h2>
                </div>
                <div className="rounded-full border border-border bg-surface px-4 py-2">
                  <span className="num text-sm font-semibold text-signal">$42.8K / month identified</span>
                </div>
              </div>
              <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
                <div className="hidden grid-cols-[0.7fr_1fr_1fr_0.45fr] bg-foreground px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.04em] text-background/75 md:grid">
                  <span>Service</span>
                  <span>CloudCare signal</span>
                  <span>Recommended action</span>
                  <span className="text-right">Impact</span>
                </div>
                {page.serviceBreakdown.map((item) => (
                  <div
                    key={item.service}
                    className="grid gap-3 border-t border-border px-5 py-5 md:grid-cols-[0.7fr_1fr_1fr_0.45fr]"
                  >
                    <h3 className="text-base font-semibold text-foreground">{item.service}</h3>
                    <p className="text-[12.5px] leading-6 text-ink-faint">{item.signal}</p>
                    <p className="text-[12.5px] leading-6 text-ink-dim">{item.action}</p>
                    <p className="num text-left text-lg font-bold text-signal md:text-right">{item.savings}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="grid gap-5 py-8 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="panel p-6">
              <div className="eyebrow">Operating flow</div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                From signal to action without losing control.
              </h2>
              <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                CloudCare collects evidence, applies policy, routes approvals, and keeps the action trail visible.
              </p>
            </div>
            <div className="grid gap-2">
              {page.workflow.map((step, index) => (
                <div key={step} className="flex items-center gap-3 rounded-lg border border-border bg-surface p-3.5">
                  <span className="num flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-[12px] text-background">
                    {index + 1}
                  </span>
                  <span className="text-sm font-semibold text-foreground">{step}</span>
                </div>
              ))}
            </div>
          </section>

          {isCostControl && page.savingsPlays && (
            <section className="py-8">
              <div className="grid gap-4 md:grid-cols-3">
                {page.savingsPlays.map((play, index) => {
                  const icons = [TrendingDown, ClipboardCheck, ShieldCheck];
                  const Icon = icons[index] ?? CheckCircle2;
                  return (
                    <article key={play.title} className="panel p-5">
                      <div className="flex items-center justify-between gap-3">
                        <span className="flex h-10 w-10 items-center justify-center rounded-md bg-accent text-signal">
                          <Icon className="size-4.5" />
                        </span>
                        <span className="rounded-full border border-border px-3 py-1 text-[11px] font-semibold text-ember">
                          {play.impact}
                        </span>
                      </div>
                      <h3 className="mt-5 text-xl font-semibold leading-tight text-foreground">{play.title}</h3>
                      <p className="mt-3 text-[12.5px] leading-relaxed text-ink-faint">{play.detail}</p>
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          <section className="py-8">
            <div className="grid gap-3 md:grid-cols-3">
              {page.outcomes.map((outcome) => (
                <div key={outcome} className="flex gap-3 rounded-lg border border-border bg-surface p-4">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />
                  <p className="text-[13px] font-medium leading-6 text-foreground">{outcome}</p>
                </div>
              ))}
            </div>
          </section>
        </main>
        <MarketingFooter />
      </div>
    </div>
  );
}
