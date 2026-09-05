"use client";

import { ArrowRight, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { S3Recommendation } from "@/lib/cloudcare-data";

/**
 * Lifecycle-suggestion-only: no delete, ACL, bucket policy, public-access,
 * or object-mutation action is possible from this view. The S3Recommendation
 * contract only carries storage-class transition fields.
 */
export function S3RecommendationsPanel({ recommendations }: { recommendations: S3Recommendation[] }) {
  const safetyNotice = (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-border/70 bg-secondary/20 px-3 py-2">
      <div className="flex min-w-0 items-center gap-2 text-[12px] text-ink-dim">
        <ShieldCheck className="size-4 shrink-0 text-[var(--mint)]" />
        <span>Lifecycle transitions only. No delete, ACL, bucket policy, public access, or object mutation action exists here.</span>
      </div>
      <Badge variant="outline" className="shrink-0 text-[10.5px]">
        recommend only
      </Badge>
    </div>
  );

  if (recommendations.length === 0) {
    return (
      <div>
        {safetyNotice}
        <p className="py-8 text-center text-[12.5px] text-ink-faint">No storage-class transition candidates found.</p>
      </div>
    );
  }

  return (
    <div>
      {safetyNotice}
      <div className="max-h-[420px] overflow-y-auto">
        <Table>
          <TableCaption>
            {recommendations.length} suggestion{recommendations.length === 1 ? "" : "s"} - lifecycle transitions only,
            nothing deleted.
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Bucket</TableHead>
              <TableHead>Transition</TableHead>
              <TableHead>Allowed change</TableHead>
              <TableHead>Evidence</TableHead>
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
                  <span className="num" style={{ color: "var(--mint)" }}>
                    {r.suggested_storage_class}
                  </span>
                </TableCell>
                <TableCell className="text-[11px] text-ink-dim">
                  <Badge variant="outline" className="whitespace-nowrap text-[10px]" style={{ color: "var(--mint)" }}>
                    lifecycle only
                  </Badge>
                  <div className="mt-1 text-[10px] text-ink-faint">No delete / ACL / policy fields</div>
                </TableCell>
                <TableCell className="num whitespace-nowrap text-[11px] text-ink-dim">
                  {typeof r.evidence?.window_days === "number" ? `${r.evidence.window_days}d` : "-"} window
                  <div className="mt-1 text-[10px] text-ink-faint">
                    {typeof r.evidence?.size_variation_pct === "number"
                      ? `${r.evidence.size_variation_pct}% size variation`
                      : "flat-size heuristic"}
                  </div>
                </TableCell>
                <TableCell className="max-w-[420px] text-[11px] leading-relaxed text-ink-faint">{r.rationale}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
