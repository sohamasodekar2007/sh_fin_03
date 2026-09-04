"use client";

import { ThemeToggle } from "@/components/cfo/ThemeToggle";
import type { Provider } from "@/lib/cloudcare-data";

/**
 * Ported from the template's ControlBar.tsx — same sticky instrument-band
 * chrome (hairline border, backdrop blur, pinned under the masthead) and
 * button-group styling. The template's scenario/period selectors don't
 * map to anything CloudCare has: there's no backend endpoint enumerating
 * connected accounts (apps/api/routers/accounts_runs.py only has POST
 * .../validate, no GET list) and no per-account region breakdown either,
 * so "account" and "region" selectors from the prompt are deliberately
 * NOT built as fake dropdowns with nothing real behind them. What IS
 * real: provider (derived from the proposals actually on hand) and a
 * time-window that genuinely drives GET /v1/focus/cost-summary's
 * period_days. This is a scoped-down honest version of item 7, not the
 * full account/region selector — flagged as a judgment call.
 */

const TIME_WINDOWS = [
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
];

interface Props {
  providers: Provider[];
  provider: Provider | "all";
  onProvider: (p: Provider | "all") => void;
  periodDays: number;
  onPeriodDays: (d: number) => void;
}

export function ControlBar({ providers, provider, onProvider, periodDays, onPeriodDays }: Props) {
  return (
    <div className="sticky top-0 z-40 -mx-4 border-b border-hairline bg-background/95 px-4 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
      <div className="grid grid-cols-1 items-center gap-2 py-2.5 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="eyebrow hidden shrink-0 text-ink-faint sm:inline">Provider</span>
          <div role="group" aria-label="Cloud provider" className="flex min-w-0 flex-initial gap-1 overflow-x-auto py-px [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {(["all", ...providers] as Array<Provider | "all">).map((p) => {
              const on = p === provider;
              return (
                <button
                  key={p}
                  type="button"
                  aria-pressed={on}
                  onClick={() => onProvider(p)}
                  className="flex min-h-9 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md border px-2.5 py-1.5 text-[12px] font-medium capitalize transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
                  style={{
                    borderColor: on ? "var(--signal)" : "var(--border)",
                    color: on ? "var(--control-on-fg)" : "var(--ink-dim)",
                    background: on ? "var(--signal)" : "var(--surface)",
                  }}
                >
                  {p === "all" ? "All providers" : p}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex min-w-0 items-center justify-end gap-2 lg:justify-self-end">
          <span className="eyebrow hidden shrink-0 text-ink-faint sm:inline">Window</span>
          <div role="group" aria-label="Time window" className="flex shrink-0 gap-px overflow-hidden rounded-md border border-border">
            {TIME_WINDOWS.map((w) => {
              const on = w.days === periodDays;
              return (
                <button
                  key={w.days}
                  type="button"
                  aria-pressed={on}
                  onClick={() => onPeriodDays(w.days)}
                  className="num min-h-9 shrink-0 px-2.5 py-1.5 text-[11px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
                  style={{ color: on ? "var(--control-on-fg)" : "var(--ink-dim)", background: on ? "var(--signal)" : "var(--surface)" }}
                >
                  {w.label}
                </button>
              );
            })}
          </div>
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
}
