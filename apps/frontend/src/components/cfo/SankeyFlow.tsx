"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  buildFlowGraph,
  centrePath,
  collapse,
  computeLayout,
  interpolate,
  nodesOnPath,
  ribbonPath,
  tracePath,
  type LinkSnap,
  type Snapshot,
  type Tone,
} from "@/lib/sankey-layout";
import { formatMoneyParts } from "@/components/Money";
import { fmtPctOr, safeDiv } from "@/lib/format";
import { useMeasure, useThemeColors } from "@/lib/motion";
import type { CostFlowRecord } from "@/lib/cloudcare-data";

/**
 * Ported from the template's SankeyFlow.tsx — same morph animation,
 * keyboard roving-cursor model, hover trace and tooltip. Remapped from
 * revenue/cost/profit tones to Provider -> ServiceCategory -> ServiceName
 * -> Environment (see src/lib/sankey-layout.ts's buildFlowGraph). Ribbon
 * opacity tokens (--ribbon-rest/lit/dim) and the travelling flow-dash
 * animation are unchanged.
 */

const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

const TONE_FILL: Record<Tone, string> = {
  provider: "url(#g-provider)",
  category: "url(#g-category)",
  service: "url(#g-service)",
  environment: "url(#g-environment)",
};

// Resolved to concrete color strings via useThemeColors below, not used as
// var() directly — see that hook's docstring for why: <stop stop-color>
// inside an inline SVG gradient doesn't reliably resolve CSS custom
// properties in every browser, unlike a plain fill/stroke attribute.
const TONE_VARS = ["--signal-deep", "--signal", "--signal-soft", "--mint"];
// Approximate light-theme fallbacks so the chart never flashes black
// before the resolver's effect runs on mount.
const FALLBACK_COLOR: Record<string, string> = {
  "--signal-deep": "#2a3f7a",
  "--signal": "#3d5aa8",
  "--signal-soft": "#6b84c2",
  "--mint": "#3f8f6f",
};

const TONE_VAR: Record<Tone, string> = {
  provider: "--signal-deep",
  category: "--signal",
  service: "--signal-soft",
  environment: "--mint",
};

interface Props {
  records: CostFlowRecord[];
  stateKey: string;
  active: boolean;
  height?: number;
}

export function SankeyFlow({ records, stateKey, active, height = 460 }: Props) {
  const { ref, width } = useMeasure<HTMLDivElement>();
  const resolvedVars = useThemeColors(TONE_VARS);
  const colorOf = (varName: string) => resolvedVars[varName] || FALLBACK_COLOR[varName];
  const TONE_STROKE: Record<Tone, string> = {
    provider: colorOf(TONE_VAR.provider),
    category: colorOf(TONE_VAR.category),
    service: colorOf(TONE_VAR.service),
    environment: colorOf(TONE_VAR.environment),
  };
  const [frame, setFrame] = useState<Snapshot | null>(null);
  const frameRef = useRef<Snapshot | null>(null);
  const rafRef = useRef(0);

  const [restingDash, setRestingDash] = useState(true);
  const [hoverLink, setHoverLink] = useState<string | null>(null);
  const [hoverNode, setHoverNode] = useState<string | null>(null);
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  const [focusKind, setFocusKind] = useState<"link" | "node" | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);

  const MIN_DIAGRAM_W = 640;
  const scrollable = width > 0 && width < MIN_DIAGRAM_W;
  const svgW = width > 0 ? Math.max(width, MIN_DIAGRAM_W) : 0;
  const compact = svgW > 0 && svgW < 860;
  const padL = compact ? 100 : 168;
  const padR = compact ? 100 : 168;
  const innerW = Math.max(220, svgW - padL - padR);
  const innerH = height - 24;

  const totalCost = useMemo(() => records.reduce((sum, r) => sum + r.BilledCost, 0), [records]);
  const graph = useMemo(() => buildFlowGraph(records), [records]);

  useEffect(() => {
    if (!active || svgW <= 0 || graph.nodes.length === 0) return;
    const target = computeLayout(graph, innerW, innerH, compact ? 9 : 12, compact ? 12 : 18);
    const first = !frameRef.current;
    const from = frameRef.current ?? collapse(target);
    const duration = first ? 1150 : 760;
    let start = 0;

    const tick = (now: number) => {
      if (!start) start = now;
      const t = Math.min(1, (now - start) / duration);
      const f = interpolate(from, target, easeInOut(t));
      frameRef.current = f;
      setFrame(f);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
      else {
        frameRef.current = target;
        setFrame(target);
      }
    };

    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);
    setRestingDash(true);
    const park = setTimeout(() => setRestingDash(false), duration + 6000);
    return () => {
      cancelAnimationFrame(rafRef.current);
      clearTimeout(park);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateKey, innerW, innerH, active, compact, graph]);

  const activeLink = hoverLink ?? (focusKind === "link" ? focusKey : null);
  const activeNode = hoverNode ?? (focusKind === "node" ? focusKey : null);

  const { litLinks, litNodes, focusLink } = useMemo(() => {
    if (!frame) return { litLinks: null as Set<string> | null, litNodes: null as Set<string> | null, focusLink: null as LinkSnap | null };
    if (activeLink && frame.links[activeLink]) {
      const l = tracePath(frame, activeLink);
      return { litLinks: l, litNodes: nodesOnPath(frame, l), focusLink: frame.links[activeLink] };
    }
    if (activeNode && frame.nodes[activeNode]) {
      const keys = new Set<string>();
      for (const k of frame.order) {
        const link = frame.links[k];
        if (link.source === activeNode || link.target === activeNode) {
          for (const t of tracePath(frame, k)) keys.add(t);
        }
      }
      return { litLinks: keys, litNodes: nodesOnPath(frame, keys), focusLink: null };
    }
    return { litLinks: null, litNodes: null, focusLink: null };
  }, [frame, activeLink, activeNode]);

  const dimmed = litLinks !== null;

  const clearFocus = () => {
    setFocusKind(null);
    setFocusKey(null);
  };

  const byY = (a: number, b: number) => a - b;

  const moveCursor = (key: string) => {
    if (!frame) return false;
    const cur = focusKind && focusKey ? { kind: focusKind, key: focusKey } : null;

    const nodesAtDepth = (depth: number) => frame.nodeOrder.filter((id) => frame.nodes[id].depth === depth).sort((a, b) => byY(frame.nodes[a].y0, frame.nodes[b].y0));
    const linksFrom = (id: string) => frame.order.filter((k) => frame.links[k].source === id).sort((a, b) => byY(frame.links[a].sy, frame.links[b].sy));
    const linksInto = (id: string) => frame.order.filter((k) => frame.links[k].target === id).sort((a, b) => byY(frame.links[a].ty, frame.links[b].ty));

    const set = (kind: "link" | "node", k: string) => {
      setFocusKind(kind);
      setFocusKey(k);
      const x = kind === "link" ? padL + (frame.links[k].sx + frame.links[k].tx) / 2 : padL + frame.nodes[k].x0;
      if (kind === "link") {
        const l = frame.links[k];
        setPointer({ x, y: 12 + (l.sy + l.ty) / 2 });
      }
      const el = ref.current;
      if (el && el.scrollWidth > el.clientWidth) {
        el.scrollTo({ left: Math.max(0, x - el.clientWidth / 2), behavior: "smooth" });
      }
      return true;
    };

    if (!cur) {
      const first = nodesAtDepth(0)[0] ?? frame.nodeOrder[0];
      return first ? set("node", first) : false;
    }

    const step = (list: string[], current: string, delta: number) => {
      const i = list.indexOf(current);
      if (i < 0 || list.length === 0) return list[0];
      return list[(i + delta + list.length) % list.length];
    };

    if (cur.kind === "node") {
      const n = frame.nodes[cur.key];
      if (!n) return false;
      if (key === "ArrowRight") {
        const out = linksFrom(cur.key)[0];
        return out ? set("link", out) : false;
      }
      if (key === "ArrowLeft") {
        const into = linksInto(cur.key)[0];
        return into ? set("link", into) : false;
      }
      const peers = nodesAtDepth(n.depth);
      return set("node", step(peers, cur.key, key === "ArrowDown" ? 1 : -1));
    }

    const l = frame.links[cur.key];
    if (!l) return false;
    if (key === "ArrowRight") return set("node", l.target);
    if (key === "ArrowLeft") return set("node", l.source);
    let peers = linksFrom(l.source);
    if (peers.length < 2) peers = linksInto(l.target);
    return set("link", step(peers, cur.key, key === "ArrowDown" ? 1 : -1));
  };

  const activeDescId = focusKind && focusKey ? (focusKind === "link" ? `sk-link-${focusKey}` : `sk-node-${focusKey}`) : undefined;

  if (records.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-md border border-dashed border-border/70 text-center text-[12.5px] text-ink-faint" style={{ height }}>
        No costed proposals yet — the flow fills in once the Analyzer and Decision agents have run.
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className={`relative select-none rounded-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)] ${scrollable ? "overflow-x-auto overflow-y-hidden" : ""}`}
      style={{ height }}
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setPointer({ x: e.clientX - r.left + e.currentTarget.scrollLeft, y: e.clientY - r.top });
      }}
      onPointerLeave={() => {
        setHoverLink(null);
        setHoverNode(null);
      }}
      tabIndex={0}
      role="application"
      aria-roledescription="Cost flow diagram"
      aria-label="Cost flow from provider through service category and service name to environment. Arrow left and right step upstream and downstream; arrow up and down move between siblings; Escape leaves the diagram."
      aria-activedescendant={activeDescId}
      onFocus={(e) => {
        if (e.target === e.currentTarget && !focusKey) moveCursor("init");
      }}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) clearFocus();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          clearFocus();
          setHoverLink(null);
          setHoverNode(null);
          (e.currentTarget as HTMLElement).blur();
          return;
        }
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
          e.preventDefault();
          moveCursor(e.key);
        }
      }}
    >
      <p className="sr-only">
        Interactive cost flow diagram. Use the left and right arrow keys to step upstream and downstream, up and down to move between
        siblings, and Escape to leave the diagram.
      </p>
      {svgW > 0 && frame && (
        <svg width={svgW} height={height} className="block overflow-visible" focusable="false">
          <defs>
            <linearGradient id="g-provider" x1="0" x2="1">
              <stop offset="0%" stopColor={colorOf("--signal-deep")} />
              <stop offset="100%" stopColor={colorOf("--signal")} />
            </linearGradient>
            <linearGradient id="g-category" x1="0" x2="1">
              <stop offset="0%" stopColor={colorOf("--signal")} />
              <stop offset="100%" stopColor={colorOf("--signal-soft")} />
            </linearGradient>
            <linearGradient id="g-service" x1="0" x2="1">
              <stop offset="0%" stopColor={colorOf("--signal-soft")} />
              <stop offset="100%" stopColor={colorOf("--mint")} />
            </linearGradient>
            <linearGradient id="g-environment" x1="0" x2="1">
              <stop offset="0%" stopColor={colorOf("--mint")} />
              <stop offset="100%" stopColor={colorOf("--mint")} />
            </linearGradient>
          </defs>

          <g transform={`translate(${padL},12)`}>
            <g>
              {frame.order.map((key) => {
                const l = frame.links[key];
                const lit = litLinks?.has(key) ?? false;
                const opacity = !dimmed ? "var(--ribbon-rest)" : lit ? "var(--ribbon-lit)" : "var(--ribbon-dim)";
                return (
                  <g key={key}>
                    <path d={ribbonPath(l)} fill={TONE_FILL[l.tone]} style={{ opacity, transition: "opacity 220ms ease-out" }} />
                    <path
                      d={centrePath(l)}
                      fill="none"
                      stroke={TONE_STROKE[l.tone]}
                      strokeWidth={lit ? 1.6 : 1}
                      strokeLinecap="round"
                      strokeDasharray="3 26"
                      className="pointer-events-none"
                      style={{
                        opacity: !dimmed ? (restingDash ? 0.28 : 0) : lit ? 0.95 : 0,
                        animationName: "flow",
                        animationDuration: `${lit ? 1.6 : 4.2}s`,
                        animationTimingFunction: "linear",
                        animationIterationCount: "infinite",
                        animationPlayState: lit || restingDash ? "running" : "paused",
                        transition: "opacity 420ms ease-out",
                      }}
                    />
                    <path
                      d={ribbonPath({ ...l, width: Math.max(l.width, 9) })}
                      fill="transparent"
                      className="cursor-crosshair focus:outline-none"
                      id={`sk-link-${key}`}
                      role="img"
                      aria-label={`${frame.nodes[l.source]?.label} to ${frame.nodes[l.target]?.label}: ${formatMoneyParts(Math.round(l.value)).usd}, ${fmtPctOr(safeDiv(l.value, totalCost), 1)} of total cost`}
                      style={{ outline: "none", stroke: focusKind === "link" && focusKey === key ? "var(--ring)" : "transparent", strokeWidth: 2 }}
                      onPointerEnter={() => {
                        setHoverLink(key);
                        setHoverNode(null);
                      }}
                    />
                  </g>
                );
              })}
            </g>

            <g>
              {frame.nodeOrder.map((id) => {
                const n = frame.nodes[id];
                const lit = litNodes?.has(id) ?? false;
                const isFirst = n.depth === 0;
                const h = Math.max(1, n.y1 - n.y0);
                const share = safeDiv(n.display, totalCost);
                return (
                  <g
                    key={id}
                    id={`sk-node-${id}`}
                    role="img"
                    aria-label={`${n.label}: ${formatMoneyParts(n.display).usd}${n.depth > 0 ? `, ${fmtPctOr(share, 0)} of total cost` : ""}`}
                    onPointerEnter={() => {
                      setHoverNode(id);
                      setHoverLink(null);
                    }}
                    className="cursor-crosshair focus:outline-none"
                  >
                    {focusKind === "node" && focusKey === id && (
                      <rect x={n.x0 - 4} y={n.y0 - 4} width={n.x1 - n.x0 + 8} height={h + 8} rx={4} fill="none" stroke="var(--ring)" strokeWidth={2} />
                    )}
                    <rect
                      x={n.x0}
                      y={n.y0}
                      width={Math.max(1, n.x1 - n.x0)}
                      height={h}
                      rx={2}
                      fill={TONE_STROKE[n.tone]}
                      style={{ opacity: !dimmed ? 0.85 : lit ? 1 : 0.18, transition: "opacity 220ms ease-out" }}
                    />
                    <rect x={n.x0 - 6} y={n.y0 - 4} width={n.x1 - n.x0 + 12} height={h + 8} fill="transparent" />
                    <g
                      transform={`translate(${isFirst ? n.x0 - 12 : n.x1 + 12},${(n.y0 + n.y1) / 2})`}
                      textAnchor={isFirst ? "end" : "start"}
                      style={{ opacity: !dimmed ? 1 : lit ? 1 : 0.3, transition: "opacity 220ms ease-out" }}
                    >
                      <text y={-3} fill="var(--foreground)" fontSize={compact ? 10 : 11.5} fontWeight={500} letterSpacing="-0.01em" stroke="var(--surface)" strokeWidth={3} strokeLinejoin="round" paintOrder="stroke">
                        {compact ? shortLabel(n.label) : n.label}
                      </text>
                      <text y={11} className="num" fill={lit || !dimmed ? "var(--ink-dim)" : "var(--ink-faint)"} fontSize={compact ? 9.5 : 10.5} stroke="var(--surface)" strokeWidth={2.6} strokeLinejoin="round" paintOrder="stroke">
                        {formatMoneyParts(n.display, { compact: true }).usd}
                        {n.depth > 0 && <tspan fill="var(--ink-faint)"> · {fmtPctOr(share, 0)}</tspan>}
                      </text>
                    </g>
                  </g>
                );
              })}
            </g>
          </g>
        </svg>
      )}

      {focusLink && frame && (
        <div
          className="pointer-events-none absolute z-20 w-56 rounded-md border border-hairline bg-popover/95 p-3 shadow-2xl backdrop-blur-sm"
          style={{ left: Math.min(Math.max(pointer.x + 16, 8), Math.max(8, svgW - 240)), top: Math.min(Math.max(pointer.y - 20, 8), height - 120) }}
        >
          <div className="eyebrow">Flow</div>
          <div className="mt-1 text-[13px] leading-snug text-foreground">
            {frame.nodes[focusLink.source]?.label}
            <span className="mx-1.5 text-ink-faint">→</span>
            {frame.nodes[focusLink.target]?.label}
          </div>
          <div className="num mt-2 text-xl font-medium text-foreground">{formatMoneyParts(Math.round(focusLink.value)).usd}</div>
          <div className="num mt-1 text-[10px] text-ink-faint">{fmtPctOr(safeDiv(focusLink.value, totalCost), 1)} of total cost</div>
        </div>
      )}
    </div>
  );
}

function shortLabel(label: string): string {
  return label.length > 14 ? `${label.slice(0, 13)}…` : label;
}
