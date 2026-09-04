import { sankey } from "d3-sankey";
import type { SankeyGraph, SankeyLink, SankeyNode } from "d3-sankey";

import type { CostFlowRecord } from "@/lib/cloudcare-data";

/**
 * Ported near-verbatim from the template's src/lib/sankey-layout.ts — the
 * layout/morph/trace engine (computeLayout, collapse, interpolate,
 * ribbonPath, centrePath, tracePath, nodesOnPath) is fully generic over
 * NDef/LDef and needed no changes at all. The only CloudCare-specific
 * piece is buildFlowGraph below, which walks FOCUS-shaped records
 * (Provider -> ServiceCategory -> ServiceName -> Environment) instead of
 * the template's revenue/cost/profit graph.
 */

export type Tone = "provider" | "category" | "service" | "environment";

export interface NDef {
  id: string;
  label: string;
  tone: Tone;
  order: number;
  display: number;
}

export interface LDef {
  source: string;
  target: string;
  value: number;
  tone: Tone;
  order: number;
}

export type LayoutNode = SankeyNode<NDef, LDef>;
export type LayoutLink = SankeyLink<NDef, LDef>;

/** Cost-flow graph: Provider -> ServiceCategory -> ServiceName -> Environment. */
export function buildFlowGraph(records: CostFlowRecord[]): { nodes: NDef[]; links: LDef[] } {
  const nodesById = new Map<string, NDef>();
  const linksByKey = new Map<string, LDef>();
  let order = 0;

  const ensureNode = (id: string, label: string, tone: Tone): NDef => {
    const existing = nodesById.get(id);
    if (existing) return existing;
    const n: NDef = { id, label, tone, order: order++, display: 0 };
    nodesById.set(id, n);
    return n;
  };

  const addLink = (sourceId: string, targetId: string, tone: Tone, value: number) => {
    const key = `${sourceId}->${targetId}`;
    const existing = linksByKey.get(key);
    if (existing) {
      existing.value += value;
    } else {
      linksByKey.set(key, { source: sourceId, target: targetId, value: Math.max(0.01, value), tone, order: order++ });
    }
  };

  for (const r of records) {
    const providerId = `p:${r.ProviderName}`;
    const categoryId = `c:${r.ProviderName}:${r.ServiceCategory}`;
    const serviceId = `s:${r.ProviderName}:${r.ServiceCategory}:${r.ServiceName}`;
    const envId = `e:${r.environment}`;

    const providerNode = ensureNode(providerId, r.ProviderName, "provider");
    const categoryNode = ensureNode(categoryId, r.ServiceCategory, "category");
    const serviceNode = ensureNode(serviceId, r.ServiceName, "service");
    const envNode = ensureNode(envId, r.environment, "environment");

    providerNode.display += r.BilledCost;
    categoryNode.display += r.BilledCost;
    serviceNode.display += r.BilledCost;
    envNode.display += r.BilledCost;

    addLink(providerId, categoryId, "provider", r.BilledCost);
    addLink(categoryId, serviceId, "category", r.BilledCost);
    addLink(serviceId, envId, "service", r.BilledCost);
  }

  return { nodes: Array.from(nodesById.values()), links: Array.from(linksByKey.values()) };
}

export interface NodeSnap {
  id: string;
  label: string;
  tone: Tone;
  depth: number;
  x0: number;
  x1: number;
  y0: number;
  y1: number;
  value: number;
  display: number;
}

export interface LinkSnap {
  key: string;
  source: string;
  target: string;
  tone: Tone;
  sx: number;
  sy: number;
  tx: number;
  ty: number;
  width: number;
  value: number;
}

export interface Snapshot {
  nodes: Record<string, NodeSnap>;
  links: Record<string, LinkSnap>;
  order: string[];
  nodeOrder: string[];
  maxDepth: number;
}

export function computeLayout(
  graph: { nodes: NDef[]; links: LDef[] },
  width: number,
  height: number,
  nodeWidth = 12,
  nodePadding = 16,
): Snapshot {
  const gen = sankey<NDef, LDef>()
    .nodeId((d) => d.id)
    .nodeWidth(nodeWidth)
    .nodePadding(nodePadding)
    .nodeSort((a, b) => (a as NDef).order - (b as NDef).order)
    .linkSort((a, b) => (a as LDef).order - (b as LDef).order)
    .extent([
      [0, 6],
      [width, height - 6],
    ]);

  const g: SankeyGraph<NDef, LDef> = gen({
    nodes: graph.nodes.map((n) => ({ ...n })),
    links: graph.links.map((l) => ({ ...l })),
  });

  const nodes: Record<string, NodeSnap> = {};
  const nodeOrder: string[] = [];
  let maxDepth = 0;
  for (const n of g.nodes as LayoutNode[]) {
    maxDepth = Math.max(maxDepth, n.depth ?? 0);
    nodes[n.id] = {
      id: n.id,
      label: n.label,
      tone: n.tone,
      depth: n.depth ?? 0,
      x0: n.x0 ?? 0,
      x1: n.x1 ?? 0,
      y0: n.y0 ?? 0,
      y1: n.y1 ?? 0,
      value: n.value ?? 0,
      display: n.display,
    };
    nodeOrder.push(n.id);
  }

  const links: Record<string, LinkSnap> = {};
  const order: string[] = [];
  for (const l of g.links as LayoutLink[]) {
    const s = l.source as LayoutNode;
    const t = l.target as LayoutNode;
    const key = `${s.id}->${t.id}`;
    links[key] = {
      key,
      source: s.id,
      target: t.id,
      tone: l.tone,
      sx: s.x1 ?? 0,
      sy: l.y0 ?? 0,
      tx: t.x0 ?? 0,
      ty: l.y1 ?? 0,
      width: l.width ?? 0,
      value: l.value as number,
    };
    order.push(key);
  }

  return { nodes, links, order, nodeOrder, maxDepth };
}

export function collapse(snap: Snapshot): Snapshot {
  const links: Record<string, LinkSnap> = {};
  for (const k of snap.order) {
    links[k] = { ...snap.links[k], width: 0, value: 0 };
  }
  const nodes: Record<string, NodeSnap> = {};
  for (const k of snap.nodeOrder) {
    const n = snap.nodes[k];
    const mid = (n.y0 + n.y1) / 2;
    nodes[k] = { ...n, y0: mid, y1: mid, value: 0, display: 0 };
  }
  return { ...snap, nodes, links };
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export function interpolate(from: Snapshot, to: Snapshot, t: number): Snapshot {
  const nodes: Record<string, NodeSnap> = {};
  for (const id of to.nodeOrder) {
    const b = to.nodes[id];
    const a = from.nodes[id] ?? b;
    nodes[id] = {
      ...b,
      x0: lerp(a.x0, b.x0, t),
      x1: lerp(a.x1, b.x1, t),
      y0: lerp(a.y0, b.y0, t),
      y1: lerp(a.y1, b.y1, t),
      value: lerp(a.value, b.value, t),
      display: lerp(a.display, b.display, t),
    };
  }

  const links: Record<string, LinkSnap> = {};
  for (const k of to.order) {
    const b = to.links[k];
    const a = from.links[k] ?? b;
    links[k] = {
      ...b,
      sx: lerp(a.sx, b.sx, t),
      sy: lerp(a.sy, b.sy, t),
      tx: lerp(a.tx, b.tx, t),
      ty: lerp(a.ty, b.ty, t),
      width: lerp(a.width, b.width, t),
      value: lerp(a.value, b.value, t),
    };
  }

  return { ...to, nodes, links };
}

export function ribbonPath(l: LinkSnap): string {
  const w = Math.max(0.4, l.width) / 2;
  const cx = (l.sx + l.tx) / 2;
  const t0 = l.sy - w;
  const t1 = l.ty - w;
  const b0 = l.sy + w;
  const b1 = l.ty + w;
  return [`M${l.sx},${t0}`, `C${cx},${t0} ${cx},${t1} ${l.tx},${t1}`, `L${l.tx},${b1}`, `C${cx},${b1} ${cx},${b0} ${l.sx},${b0}`, "Z"].join(" ");
}

export function centrePath(l: LinkSnap): string {
  const cx = (l.sx + l.tx) / 2;
  return `M${l.sx},${l.sy} C${cx},${l.sy} ${cx},${l.ty} ${l.tx},${l.ty}`;
}

export function tracePath(snap: Snapshot, linkKey: string): Set<string> {
  const out = new Set<string>([linkKey]);
  const inbound = new Map<string, string[]>();
  const outbound = new Map<string, string[]>();
  for (const k of snap.order) {
    const l = snap.links[k];
    if (!outbound.has(l.source)) outbound.set(l.source, []);
    outbound.get(l.source)!.push(k);
    if (!inbound.has(l.target)) inbound.set(l.target, []);
    inbound.get(l.target)!.push(k);
  }

  const up = (nodeId: string) => {
    for (const k of inbound.get(nodeId) ?? []) {
      if (out.has(k)) continue;
      out.add(k);
      up(snap.links[k].source);
    }
  };
  const down = (nodeId: string) => {
    for (const k of outbound.get(nodeId) ?? []) {
      if (out.has(k)) continue;
      out.add(k);
      down(snap.links[k].target);
    }
  };

  up(snap.links[linkKey].source);
  down(snap.links[linkKey].target);
  return out;
}

export function nodesOnPath(snap: Snapshot, keys: Set<string>): Set<string> {
  const s = new Set<string>();
  for (const k of keys) {
    s.add(snap.links[k].source);
    s.add(snap.links[k].target);
  }
  return s;
}
