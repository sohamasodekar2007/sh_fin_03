"use client";

import { Panel } from "@/components/cfo/Panel";
import { RDSRecommendationsPanel } from "@/components/phase14/RDSRecommendationsPanel";
import { S3RecommendationsPanel } from "@/components/phase14/S3RecommendationsPanel";
import { SecurityFindingsTable } from "@/components/phase14/SecurityFindingsTable";
import { Skeleton } from "@/components/ui/skeleton";
import { useRdsRecommendations, useS3Recommendations, useSecurityFindings } from "@/lib/queries";

/**
 * Phase 14 — Multi-Service Awareness. Every panel here is deliberately
 * non-actionable: no dollar amount on the security findings (an IAM
 * posture issue isn't a cost item), no approve/execute button on RDS or
 * S3 (both recommend-only, always) — see services/phase14/schemas.py's
 * module docstring for why that's structural, not just a UI choice.
 */
export default function SecurityFindingsPage() {
  const findingsQuery = useSecurityFindings();
  const rdsQuery = useRdsRecommendations();
  const s3Query = useS3Recommendations();

  return (
    <div className="mx-auto w-full max-w-[1400px]">
      <div className="stage py-1">
        <div className="eyebrow">Multi-service awareness</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">Security Findings</h1>
        <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-ink-faint">
          Different services get different autonomy, on purpose. EC2 can be recommended for auto-execution with
          real pre-flight checks; RDS and S3 are recommend-only, always; IAM is read-only audit — no dollar
          amount, no execute button, none of these have an autonomous path.
        </p>
      </div>

      <div className="mt-4">
        <Panel
          eyebrow="IAM · audit only"
          title="Overly broad policies"
          subtitle="Wildcard action/resource grants on real users and roles — a security posture issue, not a cost item."
          delay={100}
        >
          {findingsQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : findingsQuery.data?.error ? (
            <p className="text-[12.5px] text-destructive">Could not run the IAM review: {findingsQuery.data.error}</p>
          ) : findingsQuery.data?.enabled === false ? (
            <p className="text-[12.5px] text-ink-faint">IAM security findings are disabled (iam_security_findings_enabled=false).</p>
          ) : (
            <SecurityFindingsTable findings={findingsQuery.data?.findings ?? []} />
          )}
        </Panel>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel
          eyebrow="RDS · recommend only"
          title="Idle database candidates"
          subtitle="Never auto-executed. AWS restarts a stopped RDS instance automatically after 7 days — every recommendation says so."
          delay={220}
        >
          {rdsQuery.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : rdsQuery.data?.error ? (
            <p className="text-[12.5px] text-destructive">Could not collect RDS recommendations: {rdsQuery.data.error}</p>
          ) : rdsQuery.data?.enabled === false ? (
            <p className="text-[12.5px] text-ink-faint">RDS recommendations are disabled (rds_advisor_enabled=false).</p>
          ) : (
            <RDSRecommendationsPanel recommendations={rdsQuery.data?.recommendations ?? []} />
          )}
        </Panel>

        <Panel
          eyebrow="S3 · lifecycle suggestion only"
          title="Storage-class transitions"
          subtitle="Never a delete, never an ACL/policy change — this feature has no field that could represent either."
          delay={340}
        >
          {s3Query.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : s3Query.data?.error ? (
            <p className="text-[12.5px] text-destructive">Could not collect S3 recommendations: {s3Query.data.error}</p>
          ) : s3Query.data?.enabled === false ? (
            <p className="text-[12.5px] text-ink-faint">S3 lifecycle suggestions are disabled (s3_lifecycle_advisor_enabled=false).</p>
          ) : (
            <S3RecommendationsPanel recommendations={s3Query.data?.recommendations ?? []} />
          )}
        </Panel>
      </div>
    </div>
  );
}
