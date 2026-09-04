"use client";

import { useMemo, useState } from "react";
import { area, curveMonotoneX, line } from "d3-shape";
import { scaleLinear, scalePoint } from "d3-scale";

import { formatMoneyParts } from "@/components/Money";
import { useMeasure } from "@/lib/motion";
import type { ForecastPoint } from "@/lib/cloudcare-data";

/**
 * Ported from the template's CashFanChart.tsx — same SVG area/line
 * rendering, grid, hover crosshair and tooltip. Two real, deliberate
 * differences from the template, both about not inventing data that
 * isn't there:
 *
 * 1. GET /v1/forecasts (services/forecasting) returns one point prediction
 *    per day, not a P10/P25/P75/P90 uncertainty band — the model backtests
 *    several forecasters and returns the lowest-MAPE one's point value,
 *    nothing about its spread. The template's P10-P90/P25-P75 fan bands
 *    are dropped entirely rather than fabricated around a number with no
 *    real variance behind it.
 * 2. The HiringDrag "what-if incremental monthly hiring spend" slider has
 *    no CloudCare equivalent (there's no hiring-spend concept here) and
 *    is dropped, not repurposed into something invented.
 *
 * What's kept: the actual/predicted split maps directly onto the
 * template's historical/forecast split — solid line for actual, dashed
 * for predicted, exactly where services/forecasting's ForecastPoint
 * switches from one to the other.
 */

interface Props {
  points: ForecastPoint[];
  active: boolean;
  height?: number;
}

export function CashFanChart({ points, active, height = 240 }: Props) {
  const { ref, width } = useMeasure<HTMLDivElement>();
  const m = { top: 16, right: 56, bottom: 26, left: 8 };
  const innerW = Math.max(80, width - m.left - m.right);
  const innerH = height - m.top - m.bottom;

  const dates = useMemo(() => points.map((p) => p.date), [points]);
  const x = useMemo(() => scalePoint<string>().domain(dates).range([0, innerW]).padding(0.5), [dates, innerW]);

  const y = useMemo(() => {
    const values = points.flatMap((p) => [p.actual, p.predicted]).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (values.length === 0) return scaleLinear().domain([0, 1]).range([innerH, 0]);
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const pad = Math.max(1, (hi - lo) * 0.12);
    return scaleLinear().domain([lo - pad, hi + pad]).range([innerH, 0]);
  }, [points, innerH]);

  const actualLine = useMemo(
    () =>
      line<ForecastPoint>()
        .defined((d) => typeof d.actual === "number")
        .x((d) => x(d.date) ?? 0)
        .y((d) => y(d.actual as number))
        .curve(curveMonotoneX)(points) ?? "",
    [points, x, y],
  );
  const predictedLine = useMemo(
    () =>
      line<ForecastPoint>()
        .defined((d) => typeof d.predicted === "number")
        .x((d) => x(d.date) ?? 0)
        .y((d) => y(d.predicted as number))
        .curve(curveMonotoneX)(points) ?? "",
    [points, x, y],
  );
  const predictedBand = useMemo(
    () =>
      area<ForecastPoint>()
        .defined((d) => typeof d.predicted === "number")
        .x((d) => x(d.date) ?? 0)
        .y0(innerH)
        .y1((d) => y(d.predicted as number))
        .curve(curveMonotoneX)(points) ?? "",
    [points, x, y, innerH],
  );

  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const hovered = hoverIdx !== null ? points[hoverIdx] : null;

  if (points.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-md border border-dashed border-border/70 px-6 text-center text-[12.5px] text-ink-faint" style={{ height }}>
        No cost history yet — the forecast fills in once daily cost records exist.
      </div>
    );
  }

  return (
    <div ref={ref} className="relative" style={{ height }}>
      {width > 0 && (
        <svg
          width={width}
          height={height}
          className="block"
          onPointerMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const px = e.clientX - r.left - m.left;
            let nearest = 0;
            let nearestDist = Infinity;
            points.forEach((p, i) => {
              const d = Math.abs((x(p.date) ?? 0) - px);
              if (d < nearestDist) {
                nearestDist = d;
                nearest = i;
              }
            });
            setHoverIdx(nearest);
          }}
          onPointerLeave={() => setHoverIdx(null)}
        >
          <g transform={`translate(${m.left},${m.top})`}>
            {y.ticks(4).map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} stroke="var(--grid-line)" strokeDasharray="2 4" />
                <text x={innerW + 8} dy="0.32em" className="num" fontSize={9.5} fill="var(--ink-faint)">
                  {formatMoneyParts(t, { compact: true }).usd}
                </text>
              </g>
            ))}

            <g style={{ clipPath: active ? "inset(0 0 0 0)" : "inset(0 100% 0 0)", transition: "clip-path 1.5s cubic-bezier(0.22,1,0.36,1) 0.15s" }}>
              <path d={predictedBand} fill="var(--band-outer)" stroke="none" />
              <path d={actualLine} fill="none" stroke="var(--signal)" strokeWidth={1.75} strokeLinecap="round" />
              <path d={predictedLine} fill="none" stroke="var(--signal)" strokeWidth={1.75} strokeLinecap="round" strokeDasharray="4 3" opacity={0.85} />
            </g>

            {points.map((p, i) => (
              <text
                key={p.date}
                x={x(p.date) ?? 0}
                y={innerH + 16}
                textAnchor="middle"
                className="num"
                fontSize={8.5}
                fill={hoverIdx === i ? "var(--foreground)" : "var(--ink-faint)"}
              >
                {p.date.slice(5)}
              </text>
            ))}

            {hovered && (
              <g>
                <line x1={x(hovered.date) ?? 0} x2={x(hovered.date) ?? 0} y1={0} y2={innerH} stroke="var(--signal)" strokeOpacity={0.5} strokeDasharray="3 3" />
                <circle
                  cx={x(hovered.date) ?? 0}
                  cy={y((hovered.actual ?? hovered.predicted) as number)}
                  r={3.5}
                  fill="var(--surface)"
                  stroke="var(--signal)"
                  strokeWidth={1.75}
                />
              </g>
            )}
          </g>
        </svg>
      )}

      {hovered && (
        <div
          className="pointer-events-none absolute top-2 rounded-md border border-hairline bg-popover/95 px-3 py-2 shadow-xl"
          style={{ left: Math.min(Math.max((x(hovered.date) ?? 0) + m.left - 70, 0), Math.max(0, width - 152)) }}
        >
          <div className="eyebrow">{hovered.date}</div>
          {typeof hovered.actual === "number" && (
            <div className="num mt-0.5 text-sm text-foreground">{formatMoneyParts(hovered.actual, { compact: true }).usd} actual</div>
          )}
          {typeof hovered.predicted === "number" && (
            <div className="num mt-0.5 text-[10px] text-ink-faint">{formatMoneyParts(hovered.predicted, { compact: true }).usd} predicted</div>
          )}
        </div>
      )}

      <div className="mt-1 flex items-center gap-3 text-[10px] text-ink-faint">
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-0.5 w-3 rounded-full" style={{ background: "var(--signal)" }} /> Actual
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-0.5 w-3 rounded-full opacity-85" style={{ background: "var(--signal)", backgroundImage: "repeating-linear-gradient(90deg, var(--signal) 0 3px, transparent 3px 6px)" }} /> Predicted
        </span>
      </div>
    </div>
  );
}
