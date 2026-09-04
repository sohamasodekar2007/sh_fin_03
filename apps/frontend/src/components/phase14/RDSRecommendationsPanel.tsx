"use client";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { RDSRecommendation } from "@/lib/cloudcare-data";

/**
 * Recommend-only, always — no Approve button anywhere in this file. RDS
 * proposals never enter the real ActionProposal pipeline (see
 * services/phase14/schemas.py's module docstring), so there is nothing
 * here to wire an execute action to even if someone wanted to.
 */
export function RDSRecommendationsPanel({ recommendations }: { recommendations: RDSRecommendation[] }) {
  if (recommendations.length === 0) {
    return <p className="py-8 text-center text-[12.5px] text-ink-faint">No idle RDS instances detected.</p>;
  }

  return (
    <div className="max-h-[420px] overflow-y-auto">
      <Table>
        <TableCaption>{recommendations.length} recommendation{recommendations.length === 1 ? "" : "s"} — human approval always required.</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Instance</TableHead>
            <TableHead>Class</TableHead>
            <TableHead>Environment</TableHead>
            <TableHead className="text-right">Confidence</TableHead>
            <TableHead>Rationale</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {recommendations.map((r) => (
            <TableRow key={r.resource_id}>
              <TableCell className="num text-[11.5px]">{r.resource_id}</TableCell>
              <TableCell className="text-[11.5px] text-ink-dim">{r.db_instance_class}</TableCell>
              <TableCell className="text-[11.5px] capitalize text-ink-dim">{r.environment}</TableCell>
              <TableCell className="num text-right text-[11.5px] text-ink-dim">{Math.round(r.confidence * 100)}%</TableCell>
              <TableCell className="max-w-[420px] text-[11px] leading-relaxed text-ink-faint">{r.rationale}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
