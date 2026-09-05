"use client";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { SecurityPolicyFinding } from "@/lib/finops-api";

/**
 * Same audit-only discipline as components/phase14/SecurityFindingsTable —
 * no dollar amount, no approve/execute affordance. These four checks
 * (open ingress, unencrypted storage, public S3, stale keys) are new
 * relative to the main repo's existing IAM-wildcard-only coverage; see
 * cloudcare-fintech-addons/security_policy_addons for the source.
 */

const SEVERITY_COLOR: Record<SecurityPolicyFinding["severity"], string> = {
  low: "var(--signal)",
  medium: "var(--ember)",
  high: "var(--destructive)",
  critical: "var(--destructive)",
};

export function SecurityPolicyFindingsTable({ findings }: { findings: SecurityPolicyFinding[] }) {
  if (findings.length === 0) {
    return <p className="py-8 text-center text-[12.5px] text-ink-faint">No open-ingress, unencrypted-storage, public-bucket, or stale-key findings.</p>;
  }

  return (
    <div className="max-h-[420px] overflow-y-auto">
      <Table>
        <TableCaption>{findings.length} finding{findings.length === 1 ? "" : "s"} — audit only, no execute path exists.</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Resource</TableHead>
            <TableHead>Rule</TableHead>
            <TableHead>Severity</TableHead>
            <TableHead>Summary</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {findings.map((f) => (
            <TableRow key={f.finding_id}>
              <TableCell className="text-[11.5px]">
                <span className="capitalize text-ink-dim">{f.resource_type.replace(/_/g, " ")}</span>{" "}
                <span className="num text-foreground">{f.resource_id}</span>
              </TableCell>
              <TableCell className="num text-[11px] text-ink-faint">{f.rule_id}</TableCell>
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
