"use client";

import { useState } from "react";
import { Bot, Brain, Eye, Gavel, Sparkles } from "lucide-react";

import type { AgentActivityEntry, AgentName } from "@/lib/cloudcare-data";

/**
 * Not in the template — a new panel (item 8), built in the template's
 * visual language: eyebrow labels, hairline dividers, .num tabular
 * figures for durations, the same disclosure-row pattern ArAgingTable
 * uses for its note column, extended into a click-to-expand JSON payload.
 * Polls GET /v1/agent-activity every 30s (src/lib/queries.ts).
 */

const AGENT_ICON: Record<AgentName, typeof Eye> = {
  Monitor: Eye,
  Analyzer: Brain,
  Decision: Sparkles,
  Supervisor: Gavel,
  Executor: Bot,
};

export function AgentActivityFeed({ entries, isLoading }: { entries: AgentActivityEntry[]; isLoading: boolean }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading && entries.length === 0) {
    return (
      <div className="space-y-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-10 animate-pulse rounded-md bg-secondary/60" />
        ))}
      </div>
    );
  }

  if (entries.length === 0) {
    return <p className="text-[12.5px] leading-relaxed text-ink-faint">No agent runs recorded yet — the hourly pipeline hasn&apos;t run for this tenant.</p>;
  }

  return (
    <div className="divide-y divide-border/60">
      {entries.map((entry) => {
        const Icon = AGENT_ICON[entry.agent] ?? Eye;
        const isOpen = expanded === entry.id;
        const failed = entry.status === "failed";
        return (
          <div key={entry.id}>
            <button
              type="button"
              onClick={() => setExpanded(isOpen ? null : entry.id)}
              aria-expanded={isOpen}
              className="flex w-full items-center gap-3 py-2.5 text-left transition-colors hover:bg-secondary/30 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
            >
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                style={{ background: failed ? "color-mix(in oklab, var(--destructive) 15%, transparent)" : "var(--accent)", color: failed ? "var(--destructive)" : "var(--signal)" }}
              >
                <Icon className="size-3.5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[12.5px] font-medium text-foreground">{entry.agent}</span>
                  <span
                    className="num rounded-sm px-1 py-0.5 text-[9px] uppercase tracking-wide"
                    style={{
                      color: failed ? "var(--destructive)" : "var(--mint)",
                      background: `color-mix(in oklab, ${failed ? "var(--destructive)" : "var(--mint)"} 12%, transparent)`,
                    }}
                  >
                    {entry.status}
                  </span>
                </div>
                <p className="truncate text-[11.5px] text-ink-faint">{entry.message}</p>
              </div>
              <div className="shrink-0 text-right">
                <div className="num text-[10.5px] text-ink-dim">{entry.timestamp}</div>
                <div className="num text-[9.5px] text-ink-faint">{entry.duration_ms}ms</div>
              </div>
            </button>
            {isOpen && (
              <pre className="num max-h-56 overflow-auto rounded-md bg-surface-raised/70 p-3 text-[10.5px] leading-relaxed text-ink-dim">
                {JSON.stringify(entry.payload, null, 2)}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
