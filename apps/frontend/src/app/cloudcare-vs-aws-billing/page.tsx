import Link from "next/link";
import { ArrowRight, BadgeCheck, CircleDollarSign, ReceiptText, Sparkles, X } from "lucide-react";

import { MarketingFooter, MarketingNav } from "@/components/marketing/SolutionPage";
import { comparisonRows, comparisonVerdict } from "@/components/marketing/landing-pages";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "CloudCare vs AWS Billing | CloudCare",
  description:
    "A direct comparison of CloudCare and AWS Billing for visibility, actionability, governance, automation, and FinOps execution.",
};

export default function CloudCareVsAwsBillingPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <MarketingNav />
        <main>
          <section className="grid gap-7 py-10 lg:grid-cols-[1.08fr_0.92fr] lg:items-end lg:py-16">
            <div className="stage">
              <div className="eyebrow flex items-center gap-2">
                <ReceiptText className="size-3.5" />
                CloudCare vs AWS Billing
              </div>
              <h1 className="mt-5 max-w-4xl text-[clamp(2.35rem,5.7vw,5rem)] font-bold leading-[0.98] text-foreground">
                AWS Billing tells you what happened. CloudCare helps you decide what to do next.
              </h1>
              <p className="mt-6 max-w-3xl text-[13.5px] leading-relaxed text-ink-faint">
                AWS Billing and Cost Explorer are useful system-of-record tools. CloudCare sits above
                that layer as an action engine: it explains waste, builds proposals, enforces safety,
                and helps teams reduce spend across real resources.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href="/onboarding">
                    Launch CloudCare <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/solutions/cloud-cost-control">See cost control</Link>
                </Button>
              </div>
            </div>

            <div className="stage panel p-4" style={{ animationDelay: "160ms" }}>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-border bg-surface-raised p-5">
                  <CircleDollarSign className="size-7 text-signal" />
                  <p className="mt-5 text-2xl font-bold text-foreground">AWS Billing</p>
                  <p className="mt-2 text-[12.5px] leading-relaxed text-ink-faint">
                    Source of truth for AWS charges and billing history.
                  </p>
                </div>
                <div className="rounded-lg border border-border bg-foreground p-5 text-background">
                  <Sparkles className="size-7 text-ember" />
                  <p className="mt-5 text-2xl font-bold">CloudCare</p>
                  <p className="mt-2 text-[12.5px] leading-relaxed text-background/70">
                    AI action layer for savings decisions and execution.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section className="py-8">
            <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-card)]">
              <div className="hidden grid-cols-[0.8fr_1fr_1fr] bg-foreground px-5 py-4 text-[12px] font-semibold text-background md:grid">
                <span>Capability</span>
                <span>AWS Billing</span>
                <span>CloudCare</span>
              </div>
              {comparisonRows.map((row) => (
                <div key={row.capability} className="grid gap-4 border-t border-border px-5 py-5 md:grid-cols-[0.8fr_1fr_1fr]">
                  <h2 className="text-lg font-semibold text-foreground">{row.capability}</h2>
                  <div className="flex gap-3 text-ink-faint">
                    <X className="mt-1 size-4 shrink-0 text-destructive" />
                    <p className="text-[13px] leading-6">{row.aws}</p>
                  </div>
                  <div className="flex gap-3 text-foreground">
                    <BadgeCheck className="mt-1 size-4 shrink-0 text-mint" />
                    <p className="text-[13px] font-medium leading-6">{row.cloudcare}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-5 py-8 lg:grid-cols-[0.85fr_1.15fr]">
            <div className="panel p-6">
              <div className="eyebrow">The exact idea</div>
              <h2 className="mt-3 text-3xl font-bold leading-tight text-foreground">
                CloudCare does not replace billing truth. It upgrades what your team can do with it.
              </h2>
            </div>
            <div className="grid gap-3">
              {comparisonVerdict.map((item) => (
                <div key={item} className="rounded-lg border border-border bg-surface p-4 text-[13px] font-semibold leading-6 text-foreground">
                  {item}
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
