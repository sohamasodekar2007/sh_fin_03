"use client";

import { ArrowRight } from "lucide-react";

import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { S3Recommendation } from "@/lib/cloudcare-data";

/**
 * Lifecycle-suggestion-only — no delete, no ACL/policy change is ever
 * possible from this view, because S3Recommendation (services/phase14/
 * schemas.py) has no field that could represent one.
 */
export function S3RecommendationsPanel({ recommendations }: { recommendations: S3Recommendation[] }) {
  if (recommendations.length === 0) {
    return <p className="py-8 text-center text-[12.5px] text-ink-faint">No storage-class transition candidates found.</p>;
  }

  return (
    <div className="max-h-[420px] overflow-y-auto">
      <Table>
        <TableCaption>{recommendations.length} suggestion{recommendations.length === 1 ? "" : "s"} — lifecycle transitions only, nothing deleted.</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Bucket</TableHead>
            <TableHead>Transition</TableHead>
            <TableHead>Rationale</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {recommendations.map((r) => (
            <TableRow key={r.bucket}>
              <TableCell className="num max-w-[200px] truncate text-[11.5px]" title={r.bucket}>
                {r.bucket}
              </TableCell>
              <TableCell className="text-[11px] text-ink-dim">
                <span className="num">{r.current_storage_class}</span>
                <ArrowRight className="mx-1.5 inline size-3 text-ink-faint" />
                <span className="num" style={{ color: "var(--mint)" }}>{r.suggested_storage_class}</span>
              </TableCell>
              <TableCell className="max-w-[420px] text-[11px] leading-relaxed text-ink-faint">{r.rationale}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
