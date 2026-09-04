"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  KeyRound,
  Lock,
  RefreshCw,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type {
  AwsCoreServiceFactor,
  AwsCoreServicesExternalFactor,
  IAMGovernanceOverview,
  ResourceItem,
} from "@/lib/cloudcare-data";
import { useResources } from "@/lib/queries";

const CORE_SERVICE_FALLBACK: AwsCoreServiceFactor[] = [
  {
    service: "Amazon EC2",
    slug: "ec2",
    resource_types: ["ec2_instance", "ebs_volume"],
    purpose: "Virtual servers and attached block storage used for application compute capacity.",
    inventory_status: "implemented",
    collector_actions: ["ec2:DescribeInstances", "ec2:DescribeVolumes", "autoscaling:DescribeAutoScalingGroups"],
    read_only_policies: ["AmazonEC2ReadOnlyAccess", "CloudWatchReadOnlyAccess"],
    full_access_policies: ["AmazonEC2FullAccess"],
    approved_executor_actions: ["ec2:StartInstances", "ec2:StopInstances", "ec2:ModifyInstanceAttribute"],
    blocked_executor_actions: ["ec2:TerminateInstances"],
    rules: [
      "Flag idle instances only with real CPU/network evidence.",
      "Do not stop ASG-backed instances without ASG context.",
      "Require human approval before live mutation.",
    ],
    risk_notes: "Stopping is reversible; termination is intentionally excluded.",
  },
  {
    service: "Amazon S3",
    slug: "s3",
    resource_types: ["s3_bucket"],
    purpose: "Durable object storage for files, backups, logs, exports, and static assets.",
    inventory_status: "implemented",
    collector_actions: ["s3:ListAllMyBuckets", "s3:GetBucketLocation", "s3:GetBucketTagging"],
    read_only_policies: ["AmazonS3ReadOnlyAccess"],
    full_access_policies: ["AmazonS3FullAccess"],
    approved_executor_actions: ["s3:PutLifecycleConfiguration", "s3:PutBucketTagging"],
    blocked_executor_actions: ["s3:DeleteBucket", "s3:DeleteObject"],
    rules: [
      "Show the FOCUS export bucket and lifecycle posture.",
      "Recommend lifecycle only with supporting usage evidence.",
      "Do not read object contents for inventory collection.",
    ],
    risk_notes: "Bucket and object deletion are destructive and are not automatic.",
  },
  {
    service: "Amazon RDS",
    slug: "rds",
    resource_types: ["rds_instance"],
    purpose: "Managed relational databases such as PostgreSQL, MySQL, MariaDB, Oracle, and SQL Server.",
    inventory_status: "implemented",
    collector_actions: ["rds:DescribeDBInstances", "rds:ListTagsForResource", "cloudwatch:GetMetricStatistics"],
    read_only_policies: ["AmazonRDSReadOnlyAccess"],
    full_access_policies: ["AmazonRDSFullAccess"],
    approved_executor_actions: ["rds:StartDBInstance", "rds:StopDBInstance", "rds:ModifyDBInstance"],
    blocked_executor_actions: ["rds:DeleteDBInstance"],
    rules: [
      "Show Multi-AZ and deletion-protection context.",
      "Require connection and CPU evidence before stop recommendations.",
      "Keep all database mutations human-approved.",
    ],
    risk_notes: "Database changes can create downtime; deletion is excluded.",
  },
  {
    service: "AWS Lambda",
    slug: "lambda",
    resource_types: ["lambda_function"],
    purpose: "Serverless functions that execute code in response to events.",
    inventory_status: "implemented",
    collector_actions: ["lambda:ListFunctions", "lambda:ListTags", "cloudwatch:GetMetricData"],
    read_only_policies: ["AWSLambda_ReadOnlyAccess"],
    full_access_policies: ["AWSLambda_FullAccess"],
    approved_executor_actions: ["lambda:UpdateFunctionConfiguration", "lambda:PutFunctionConcurrency"],
    blocked_executor_actions: ["lambda:DeleteFunction"],
    rules: [
      "Surface runtime, state, tags, and cost context.",
      "Scope iam:PassRole when creation/update support is added.",
      "Do not delete functions automatically.",
    ],
    risk_notes: "Function config updates can affect production event flows.",
  },
  {
    service: "Amazon VPC",
    slug: "vpc",
    resource_types: ["vpc"],
    purpose: "Isolated networking boundary for subnets, routing, security groups, gateways, and endpoints.",
    inventory_status: "implemented",
    collector_actions: ["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"],
    read_only_policies: ["AmazonVPCReadOnlyAccess", "AmazonEC2ReadOnlyAccess"],
    full_access_policies: ["AmazonVPCFullAccess"],
    approved_executor_actions: ["ec2:CreateTags"],
    blocked_executor_actions: ["ec2:DeleteVpc", "ec2:DeleteSubnet"],
    rules: [
      "Use VPC inventory as dependency context.",
      "Treat routing/security-group changes as security-reviewed.",
      "Never delete network primitives from cost automation.",
    ],
    risk_notes: "Networking changes can take applications offline.",
  },
  {
    service: "AWS IAM",
    slug: "iam",
    resource_types: ["iam_user"],
    purpose: "Identity, access, roles, policies, account posture, and audit visibility.",
    inventory_status: "implemented",
    collector_actions: ["iam:GetAccountSummary", "iam:GetAccountAuthorizationDetails", "cloudtrail:LookupEvents"],
    read_only_policies: ["IAMReadOnlyAccess", "AWSCloudTrail_ReadOnlyAccess"],
    full_access_policies: ["IAMFullAccess"],
    approved_executor_actions: [],
    blocked_executor_actions: ["iam:*"],
    rules: [
      "Detect admin policies, stale keys, root posture, and creator attribution.",
      "Do not let the app grant IAM permissions to itself.",
      "Use separate read and executor roles with ExternalId.",
    ],
    risk_notes: "IAM write access can become privilege escalation.",
  },
  {
    service: "Amazon DynamoDB",
    slug: "dynamodb",
    resource_types: ["dynamodb_table"],
    purpose: "Managed NoSQL tables for high-throughput, low-latency workloads.",
    inventory_status: "implemented",
    collector_actions: ["dynamodb:ListTables", "dynamodb:DescribeTable", "dynamodb:ListTagsOfResource"],
    read_only_policies: ["AmazonDynamoDBReadOnlyAccess"],
    full_access_policies: ["AmazonDynamoDBFullAccess_v2"],
    approved_executor_actions: ["dynamodb:UpdateTable", "dynamodb:UpdateContinuousBackups"],
    blocked_executor_actions: ["dynamodb:DeleteTable"],
    rules: [
      "Surface billing mode, table status, tags, and backup posture.",
      "Prefer capacity/billing optimization over destructive table actions.",
      "Use AmazonDynamoDBFullAccess_v2 for full-access setup.",
    ],
    risk_notes: "Table deletion is data loss and is excluded.",
  },
  {
    service: "Amazon CloudFront",
    slug: "cloudfront",
    resource_types: ["cloudfront_distribution"],
    purpose: "Global CDN for static and dynamic web content distribution.",
    inventory_status: "implemented",
    collector_actions: ["cloudfront:ListDistributions", "cloudfront:ListTagsForResource", "cloudfront:GetDistributionConfig"],
    read_only_policies: ["CloudFrontReadOnlyAccess"],
    full_access_policies: ["CloudFrontFullAccess"],
    approved_executor_actions: ["cloudfront:UpdateDistribution", "cloudfront:CreateInvalidation"],
    blocked_executor_actions: ["cloudfront:DeleteDistribution"],
    rules: [
      "Show enabled state, price class, aliases, and origin context.",
      "Require ETag-aware distribution updates.",
      "Do not delete distributions automatically.",
    ],
    risk_notes: "Distribution updates can affect global traffic.",
  },
];

const DISCOVERY_POLICY_FALLBACK = [
  "ViewOnlyAccess",
  "CloudWatchReadOnlyAccess",
  "AWSBillingReadOnlyAccess",
  "ComputeOptimizerReadOnlyAccess",
  "CostOptimizationHubReadOnlyAccess",
  "ResourceGroupsandTagEditorReadOnlyAccess",
  "AWSCloudTrail_ReadOnlyAccess",
];

const EXECUTOR_BOUNDARY_FALLBACK = {
  allowed_pattern: "Only explicitly listed start/stop/resize/tag/capacity/configuration actions after approval.",
  excluded: [
    "iam:*",
    "organizations:*",
    "account:*",
    "s3:DeleteBucket",
    "s3:DeleteObject",
    "rds:DeleteDBInstance",
    "dynamodb:DeleteTable",
    "cloudtrail:StopLogging",
    "cloudtrail:DeleteTrail",
  ],
  required_gates: [
    "EXECUTION_ENABLED=true",
    "EXECUTION_MODE=live for real AWS mutation",
    "proposal status is approved",
    "current live tags pass policy engine",
    "resource has the configured execution allowlist tag",
    "executor writes an audit log",
  ],
};

const SERVICE_ICONS: Record<string, typeof Database> = {
  ec2: Zap,
  s3: Database,
  rds: Database,
  lambda: Zap,
  vpc: Lock,
  iam: KeyRound,
  dynamodb: Database,
  cloudfront: ShieldCheck,
};

function byResourceType(resources: ResourceItem[]) {
  return resources.reduce<Record<string, number>>((acc, resource) => {
    const type = resource.resource_type ?? "unknown";
    acc[type] = (acc[type] ?? 0) + 1;
    return acc;
  }, {});
}

function compactList(items: string[], limit = 3) {
  if (items.length <= limit) return items.join(", ");
  return `${items.slice(0, limit).join(", ")} +${items.length - limit}`;
}

function serviceResources(resources: ResourceItem[], resourceTypes: string[]) {
  return resources.filter((resource) => resource.resource_type && resourceTypes.includes(resource.resource_type));
}

export default function AwsCoreServicesPage() {
  const resourcesQuery = useResources();
  const factorQuery = useQuery({
    queryKey: ["aws-core-services-external-factor"],
    queryFn: () => api.get<AwsCoreServicesExternalFactor>("/v1/external-factors/aws-core-services"),
  });
  const governanceQuery = useQuery({
    queryKey: ["aws-core-services-iam-governance"],
    queryFn: () => api.get<IAMGovernanceOverview>("/v1/governance/iam-overview"),
  });

  const resources = useMemo(() => resourcesQuery.data ?? [], [resourcesQuery.data]);
  const counts = useMemo(() => byResourceType(resources), [resources]);
  const services = factorQuery.data?.services?.length ? factorQuery.data.services : CORE_SERVICE_FALLBACK;
  const discoveryPolicies = factorQuery.data?.discovery_role_recommendations?.length
    ? factorQuery.data.discovery_role_recommendations
    : DISCOVERY_POLICY_FALLBACK;
  const executorBoundary = factorQuery.data?.executor_role_boundaries ?? EXECUTOR_BOUNDARY_FALLBACK;
  const focusStats = useMemo(() => {
    const version = resources.find((resource) => resource.focus_version)?.focus_version ?? "1.2";
    const liveRows = resources.filter((resource) => resource.cost_source === "focus_live_export");
    const totalRows = resources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0);
    const costed = resources.filter((resource) => resource.monthly_cost_usd !== null).length;
    const liveExportRows = liveRows.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0);
    return {
      version,
      totalRows,
      liveExportRows,
      costed,
      source: resources.find((resource) => resource.focus_source)?.focus_source ?? "waiting",
    };
  }, [resources]);
  const totalMappedResources = services.reduce(
    (sum, service) => sum + service.resource_types.reduce((inner, type) => inner + (counts[type] ?? 0), 0),
    0,
  );

  const refreshing = factorQuery.isFetching || resourcesQuery.isFetching || governanceQuery.isFetching;

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage py-1">
        <div className="eyebrow">External factor</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">
          AWS core services
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{services.length || 8} services</Badge>
          <Badge variant="outline">{totalMappedResources} discovered resources</Badge>
          <Badge variant={focusStats.liveExportRows > 0 ? "secondary" : "outline"}>FOCUS {focusStats.version}</Badge>
          <Badge variant="outline">{focusStats.liveExportRows} live-export rows</Badge>
          <Badge variant="outline">{factorQuery.data?.source ?? "external_factor.aws_core_services"}</Badge>
          {factorQuery.isError ? <Badge variant="destructive">metadata fallback</Badge> : null}
          <Button
            size="sm"
            variant="outline"
            disabled={refreshing}
            onClick={() => {
              factorQuery.refetch();
              resourcesQuery.refetch();
              governanceQuery.refetch();
            }}
          >
            <RefreshCw className={refreshing ? "size-3.5 animate-spin" : "size-3.5"} />
            {refreshing ? "Refreshing" : "Refresh"}
          </Button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.42fr)]">
        <Panel title="Service coverage" eyebrow="Inventory + rules" delay={100}>
          {factorQuery.isLoading && !services.length ? (
            <Skeleton className="h-[520px] w-full" />
          ) : (
            <div className="grid gap-3 xl:grid-cols-2">
              {services.map((service) => {
                const Icon = SERVICE_ICONS[service.slug] ?? Database;
                const matchedResources = serviceResources(resources, service.resource_types);
                const governanceError = service.slug === "iam" ? governanceQuery.data?.errors?.users : undefined;
                const discovered = service.slug === "iam" && governanceQuery.data?.users
                  ? governanceQuery.data.users.length
                  : matchedResources.length;
                const focusRows = matchedResources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0);
                const costed = matchedResources.filter((resource) => resource.monthly_cost_usd !== null).length;
                return (
                  <article key={service.slug} className="rounded-md border border-border bg-background p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="grid size-10 shrink-0 place-items-center rounded-md border border-border bg-card">
                          <Icon className="size-4 text-ink-dim" />
                        </div>
                        <div className="min-w-0">
                          <h2 className="truncate text-[14px] font-semibold text-foreground">{service.service}</h2>
                          <p className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-ink-faint">{service.purpose}</p>
                        </div>
                      </div>
                      <Badge
                        variant={governanceError ? "destructive" : service.inventory_status === "implemented" ? "secondary" : "outline"}
                        className="shrink-0"
                      >
                        {governanceError ? "AccessDenied" : discovered}
                      </Badge>
                    </div>

                    <div className="mt-4 grid gap-2 text-[11.5px]">
                      <div className="rounded border border-border bg-card px-3 py-2">
                        <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Resource types</div>
                        <div className="num mt-1 text-ink-dim">{service.resource_types.join(", ")}</div>
                      </div>
                      <div className="rounded border border-border bg-card px-3 py-2">
                        <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                          {service.slug === "iam" ? "Governance coverage" : "FOCUS coverage"}
                        </div>
                        <div className="num mt-1 text-ink-dim">
                          {service.slug === "iam"
                            ? governanceError
                              ? governanceError
                              : `${discovered} IAM users - not a FOCUS cost resource`
                            : `${focusRows} rows - ${costed}/${discovered} costed`}
                        </div>
                      </div>
                      <div className="rounded border border-border bg-card px-3 py-2">
                        <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Read policies</div>
                        <div className="mt-1 text-ink-dim">{compactList(service.read_only_policies)}</div>
                      </div>
                      <div className="rounded border border-border bg-card px-3 py-2">
                        <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Full access policies</div>
                        <div className="mt-1 text-ink-dim">{compactList(service.full_access_policies)}</div>
                      </div>
                    </div>

                    <div className="mt-4 space-y-1.5">
                      {service.rules.slice(0, 3).map((rule) => (
                        <div key={rule} className="flex gap-2 text-[11.5px] leading-relaxed text-ink-dim">
                          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-[var(--mint)]" />
                          <span>{rule}</span>
                        </div>
                      ))}
                    </div>

                    <div className="mt-4 rounded border border-border bg-card px-3 py-2 text-[11.5px] leading-relaxed text-ink-faint">
                      {service.risk_notes}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </Panel>

        <div className="space-y-3">
          <Panel title="FOCUS 1.2 feed" eyebrow="Cost join" delay={120}>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-md border border-border bg-background px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Version</div>
                <div className="num mt-1 text-[15px] font-semibold text-foreground">{focusStats.version}</div>
              </div>
              <div className="rounded-md border border-border bg-background px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Source</div>
                <div className="num mt-1 truncate text-[15px] font-semibold text-foreground">{focusStats.source}</div>
              </div>
              <div className="rounded-md border border-border bg-background px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Rows</div>
                <div className="num mt-1 text-[15px] font-semibold text-foreground">{focusStats.totalRows}</div>
              </div>
              <div className="rounded-md border border-border bg-background px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Costed</div>
                <div className="num mt-1 text-[15px] font-semibold text-foreground">
                  {focusStats.costed}/{resources.length}
                </div>
              </div>
            </div>
          </Panel>

          <Panel title="Discovery role" eyebrow="Read path" delay={140}>
            <div className="space-y-2">
              {discoveryPolicies.map((policy) => (
                <div key={policy} className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2">
                  <span className="text-[12px] text-ink-dim">{policy}</span>
                  <Badge variant="outline">read</Badge>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Executor boundary" eyebrow="Write path" delay={180}>
            <p className="text-[12.5px] leading-relaxed text-ink-dim">
              {executorBoundary.allowed_pattern}
            </p>
            <div className="mt-4 space-y-1.5">
              {executorBoundary.required_gates.map((gate) => (
                <div key={gate} className="flex gap-2 text-[11.5px] leading-relaxed text-ink-dim">
                  <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-[var(--signal)]" />
                  <span>{gate}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Blocked actions" eyebrow="Never automatic" delay={220}>
            <div className="flex flex-wrap gap-1.5">
              {executorBoundary.excluded.map((action) => (
                <Badge key={action} variant="destructive" className="text-[10px]">
                  <AlertTriangle className="size-3" />
                  {action}
                </Badge>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
