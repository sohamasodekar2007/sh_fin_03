"use client";

import { useMemo, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { scaleLinear } from "d3-scale";

import { formatMoneyParts } from "@/components/Money";
import { useStage } from "@/lib/motion";
import { waterfallStepColor, type WaterfallStep } from "@/lib/cloudcare-data";

/**
 * Ported from the template's VarianceWaterfall.tsx — same SVG bar-chart
 * geometry, connectors, focus rings and stagger timing. Remapped from
 * budget→actual operating-income variance to current→optimized monthly
 * cost (services/supervisor/service.py's scored proposals): the opening
 * anchor is current monthly cost, one delta bar per proposal (negative =
 * savings), the closing anchor is optimized monthly cost. Colored by
 * status per the prompt: approved --mint, pending --signal, rejected
 * --graphite (see lib/cloudcare-data.ts's waterfallStepColor).
 */

interface Props {
  steps: WaterfallStep[];
  active: boolean;
  selected: string | null;
  onSelect: (key: string | null) => void;
}

export function VarianceWaterfall({ steps, active, selected, onSelect }: Props) {
  const [containerRef, setContainerRef] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);

  const measuredRef = (el: HTMLDivElement | null) => {
    setContainerRef(el);
    if (el) setWidth(el.getBoundingClientRect().width);
  };

  useMemo(() => {
    if (!containerRef) return;
    const ro = new ResizeObserver(() => setWidth(containerRef.getBoundingClientRect().width));
    ro.observe(containerRef);
    return () => ro.disconnect();
  }, [containerRef]);

  const height = 236;
  const m = { top: 22, right: 56, bottom: 38, left: 8 };
  const innerW = Math.max(120, width - m.left - m.right);
  const innerH = height - m.top - m.bottom;

  const y = useMemo(() => {
    if (steps.length === 0) return scaleLinear().domain([0, 1]).range([innerH, 0]);
    const vals = steps.flatMap((s) => [s.start, s.end, 0]);
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const pad = (hi - lo) * 0.05 || 1;
    return scaleLinear().domain([lo - pad, hi + pad]).range([innerH, 0]);
  }, [steps, innerH]);

  const bandW = steps.length > 0 ? innerW / steps.length : innerW;
  const barW = Math.min(46, bandW * 0.56);
  const started = useStage(active ? 60 : 100000);
  const [focusedKey, setFocusedKey] = useState<string | null>(null);

  if (steps.length === 0) {
    return (
      <div className="flex h-[236px] items-center justify-center rounded-md border border-dashed border-border/70 px-6 text-center text-[12.5px] text-ink-faint">
        No proposals awaiting a decision — nothing to show in the transition yet.
      </div>
    );
  }

  return (
    <div ref={measuredRef} className="relative" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} className="block">
          <g transform={`translate(${m.left},${m.top})`}>
            {y.ticks(4).map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line
                  x2={innerW}
                  stroke={t === 0 ? "var(--axis-line)" : "var(--grid-line)"}
                  strokeOpacity={t === 0 ? 1 : 0.85}
                  strokeDasharray={t === 0 ? undefined : "2 4"}
                />
                <text x={innerW + 8} dy="0.32em" className="num" fontSize={9.5} fill="var(--ink-faint)">
                  {formatMoneyParts(t, { compact: true }).usd}
                </text>
              </g>
            ))}

            {steps.map((s, i) => {
              const cx = i * bandW + bandW / 2;
              const top = y(Math.max(s.start, s.end));
              const bottom = y(Math.min(s.start, s.end));
              const h = Math.max(2, bottom - top);
              const isAnchor = s.kind === "anchor";
              const fill = waterfallStepColor(s);
              const isSel = selected === s.key;
              const dim = selected !== null && !isSel;
              const grows = s.end >= s.start;
              const parts = formatMoneyParts(isAnchor ? s.end : Math.abs(s.impact), { compact: true });

              return (
                <g key={s.key}>
                  {i > 0 && !isAnchor && (
                    <line
                      x1={(i - 1) * bandW + bandW / 2 + barW / 2}
                      x2={cx - barW / 2}
                      y1={y(s.start)}
                      y2={y(s.start)}
                      stroke="var(--connector)"
                      strokeWidth={1}
                      strokeDasharray="3 2"
                      style={{ opacity: started ? 0.8 : 0, transition: `opacity 300ms ease-out ${140 + i * 130}ms` }}
                    />
                  )}

                  <g
                    className={s.proposal ? "cursor-pointer focus:outline-none" : ""}
                    onClick={() => s.proposal && onSelect(isSel ? null : s.key)}
                    {...(s.proposal
                      ? {
                          role: "button",
                          tabIndex: 0,
                          "aria-pressed": isSel,
                          "aria-label": `${s.label}: ${s.impact <= 0 ? "saves" : "costs"} ${parts.usd} per month. Status ${s.proposal.status}. Open detail.`,
                          onFocus: () => setFocusedKey(s.key),
                          onBlur: () => setFocusedKey((k) => (k === s.key ? null : k)),
                          onKeyDown: (e: ReactKeyboardEvent) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              onSelect(isSel ? null : s.key);
                            }
                          },
                        }
                      : { "aria-hidden": true })}
                  >
                    <rect x={cx - bandW / 2} y={0} width={bandW} height={innerH} fill="transparent" />
                    <rect
                      x={cx - barW / 2}
                      y={top}
                      width={barW}
                      height={h}
                      rx={2}
                      fill={fill}
                      style={{
                        transformBox: "fill-box",
                        transformOrigin: grows ? "center bottom" : "center top",
                        transform: started ? "scaleY(1)" : "scaleY(0)",
                        opacity: started ? (dim ? 0.28 : 1) : 0,
                        transition: `transform 520ms cubic-bezier(0.22,1,0.36,1) ${i * 130}ms, opacity 300ms ease-out ${i * 130}ms`,
                      }}
                    />
                    {focusedKey === s.key && (
                      <rect x={cx - barW / 2 - 2} y={top - 2} width={barW + 4} height={h + 4} rx={3} fill="none" stroke="var(--ring)" strokeWidth={2} />
                    )}
                    {isSel && (
                      <rect x={cx - barW / 2 - 3} y={top - 3} width={barW + 6} height={h + 6} rx={4} fill="none" stroke="var(--signal)" strokeWidth={1.25} />
                    )}

                    <text
                      x={cx}
                      y={grows ? top - 7 : bottom + 13}
                      textAnchor="middle"
                      className="num"
                      fontSize={9.5}
                      fill={isAnchor ? "var(--foreground)" : fill}
                      style={{ opacity: started ? (dim ? 0.4 : 1) : 0, transition: `opacity 340ms ease-out ${240 + i * 130}ms` }}
                    >
                      {isAnchor ? parts.usd : `${s.impact <= 0 ? "−" : "+"}${parts.usd}`}
                    </text>
                  </g>

                  <text
                    x={cx}
                    y={innerH + 18}
                    textAnchor="middle"
                    fontSize={9}
                    fill={isSel ? "var(--foreground)" : "var(--ink-faint)"}
                    style={{ opacity: started ? 1 : 0, transition: `opacity 340ms ease-out ${200 + i * 130}ms` }}
                  >
                    {abbrev(s.label)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      )}
    </div>
  );
}

function abbrev(label: string): string {
  if (label === "Current monthly cost") return "Current";
  if (label === "Optimized monthly cost") return "Optimized";
  return label.length > 16 ? `${label.slice(0, 15)}…` : label;
}
