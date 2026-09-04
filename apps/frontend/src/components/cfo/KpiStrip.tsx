"use client";

import { useId, useState } from "react";

import { Money } from "@/components/Money";
import { NOT_AVAILABLE, fmtPct, isNum } from "@/lib/format";
import { useCountUp } from "@/lib/motion";

type Fmt = "usd" | "usdCompact" | "pct" | "months" | "count";

const countFormatter = new Intl.NumberFormat("en-US");

export interface Kpi {
  label: string;
  /** null when the figure is not computable from the data. */
  value: number | null;
  fmt: Fmt;
  /** null when there is no comparable prior period. */
  delta: number | null;
  deltaLabel: string;
  hint: string;
  tone?: "signal" | "ember" | "mint";
}

function render(value: number, fmt: Fmt) {
  switch (fmt) {
    case "pct":
      return fmtPct(value, 1);
    case "months":
      return `${value.toFixed(1)}`;
    case "count":
      return countFormatter.format(Math.round(value));
    default:
      return "";
  }
}

function KpiCell({ kpi, index }: { kpi: Kpi; index: number }) {
  const available = isNum(kpi.value);
  const v = useCountUp(available ? (kpi.value as number) : 0, 1500, 220 + index * 110);
  const up = (kpi.delta ?? 0) >= 0;

  /**
   * FLIP MODEL — three independent triggers, one visual state.
   *   hover   pointer devices only (a touch tap must not leave a card stuck)
   *   focus   keyboard only (:focus-visible), so a tap does not latch the flip
   *   pinned  tap / click toggle, the touch path
   * The count-up lives above this state, so flipping never restarts a ticker.
   */
  const [hover, setHover] = useState(false);
  const [kbFocus, setKbFocus] = useState(false);
  const [pinned, setPinned] = useState(false);
  const flipped = hover || kbFocus || pinned;

  const hintId = useId();

  return (
    <button
      type="button"
      aria-describedby={hintId}
      aria-pressed={pinned}
      onClick={() => setPinned((p) => !p)}
      onPointerEnter={(e) => {
        if (e.pointerType === "mouse") setHover(true);
      }}
      onPointerLeave={() => setHover(false)}
      onFocus={(e) => {
        if (e.currentTarget.matches(":focus-visible")) setKbFocus(true);
      }}
      onBlur={() => setKbFocus(false)}
      className="stage group relative block w-full flex-1 cursor-pointer text-left outline-none focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
      style={{ animationDelay: `${140 + index * 90}ms`, perspective: "900px" }}
    >
      <div
        className="relative transition-transform duration-[520ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
        style={{
          transformStyle: "preserve-3d",
          transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)",
        }}
      >
        {/* ---- front: the figure, unchanged ---- */}
        <div
          className="px-5 py-3 lg:px-6"
          style={{ backfaceVisibility: "hidden" }}
        >
          <div className="flex items-baseline gap-2">
            <span className="eyebrow">{kpi.label}</span>
          </div>

          <div className="mt-1.5 flex items-end gap-2">
            {kpi.fmt === "usd" || kpi.fmt === "usdCompact" ? (
              <Money
                value={available ? v : null}
                compact={kpi.fmt === "usdCompact"}
                className="text-[clamp(1.45rem,2.1vw,2.15rem)] font-medium leading-none"
                style={{
                  color: !available
                    ? "var(--ink-faint)"
                    : kpi.tone === "ember"
                      ? "var(--ember)"
                      : kpi.tone === "mint"
                        ? "var(--mint)"
                        : "var(--foreground)",
                }}
              />
            ) : (
              <span
                className="num text-[clamp(1.45rem,2.1vw,2.15rem)] font-medium leading-none"
                style={{
                  color: !available
                    ? "var(--ink-faint)"
                    : kpi.tone === "ember"
                      ? "var(--ember)"
                      : kpi.tone === "mint"
                        ? "var(--mint)"
                        : "var(--foreground)",
                }}
              >
                {available ? render(v, kpi.fmt) : NOT_AVAILABLE}
              </span>
            )}
            {available && kpi.fmt === "months" && (
              <span className="mb-0.5 text-[11px] text-ink-faint">months</span>
            )}
          </div>

          <div className="mt-1.5 flex items-center gap-1.5">
            {isNum(kpi.delta) ? (
              <span
                className="num text-[10.5px]"
                style={{ color: up ? "var(--mint)" : "var(--ember)" }}
              >
                {up ? "▲" : "▼"} {Math.abs(kpi.delta).toFixed(1)}%
              </span>
            ) : (
              <span className="num text-[10.5px] text-ink-faint">{NOT_AVAILABLE}</span>
            )}
            <span className="text-[10.5px] text-ink-faint">{kpi.deltaLabel}</span>
          </div>
        </div>

        {/* ---- back: the definition. Absolute so the strip never reflows. ---- */}
        <div
          className="absolute inset-0 flex flex-col justify-center bg-surface px-5 py-3 lg:px-6"
          style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
        >
          <span className="eyebrow">{kpi.label}</span>
          <span
            id={hintId}
            className="mt-1.5 text-[11.5px] leading-snug text-ink-dim"
          >
            {kpi.hint}
          </span>
        </div>
      </div>
    </button>
  );
}

export function KpiStrip({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className="panel hairline-top grid grid-cols-2 divide-x divide-y divide-border/70 sm:grid-cols-3 lg:grid-cols-5 lg:divide-y-0">
      {kpis.map((k, i) => (
        <KpiCell key={k.label} kpi={k} index={i} />
      ))}
    </div>
  );
}
