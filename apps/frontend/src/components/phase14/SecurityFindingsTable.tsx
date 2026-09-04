"use client";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { SecurityFinding } from "@/lib/cloudcare-data";

/**
 * Read-only, always — no dollar amount, no approve/execute affordance
 * anywhere in this file. An IAM finding is a security posture issue, not
 * a cost recommendation, and this table is deliberately built so nobody
 * could mistake one for the other.
 */

const SEVERITY_COLOR: Record<SecurityFinding["severity"], string> = {
  low: "var(--signal)",
  medium: "var(--ember)",
  high: "var(--destructive)",
  critical: "var(--destructive)",
};

export function SecurityFindingsTable({ findings }: { findings: SecurityFinding[] }) {
  if (findings.length === 0) {
    return <p className="py-8 text-center text-[12.5px] text-ink-faint">No overly-broad IAM policies found.</p>;
  }

  return (
    <div className="max-h-[420px] overflow-y-auto">
      <Table>
        <TableCaption>{findings.length} finding{findings.length === 1 ? "" : "s"} — audit only, no execute path exists.</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Principal</TableHead>
            <TableHead>Policy</TableHead>
            <TableHead>Severity</TableHead>
            <TableHead>Summary</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {findings.map((f) => (
            <TableRow key={f.finding_id}>
              <TableCell className="text-[11.5px]">
                <span className="capitalize text-ink-dim">{f.principal_type}</span>{" "}
                <span className="num text-foreground">{f.principal_name}</span>
              </TableCell>
              <TableCell className="text-[11.5px] text-ink-dim">
                {f.policy_name} <span className="text-[10px] text-ink-faint">({f.policy_type})</span>
              </TableCell>
              <TableCell>
                <Badge
                  variant="outline"
                  className="text-[10px] uppercase"
                  style={{ color: SEVERITY_COLOR[f.severity], borderColor: `color-mix(in oklab, ${SEVERITY_COLOR[f.severity]} 40%, transparent)` }}
                >
                  {f.severity}
                </Badge>
              </TableCell>
              <TableCell className="max-w-[360px] text-[11.5px] text-ink-dim">{f.summary}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
