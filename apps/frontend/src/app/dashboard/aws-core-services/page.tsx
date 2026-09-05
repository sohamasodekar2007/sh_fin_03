"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Database,
  FileJson,
  KeyRound,
  Lock,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, isApiError } from "@/lib/api";
import type {
  AwsCoreServiceFactor,
  AwsCoreServicesExternalFactor,
  IAMGovernanceOverview,
  ResourceItem,
} from "@/lib/cloudcare-data";
import { useResources } from "@/lib/queries";

type CoverageFilter = "all" | "with_resources" | "implemented" | "planned";
type DetailSection = "overview" | "aws-data" | "resources" | "permissions" | "rules" | "raw";

interface ServiceBlueprint {
  focus: string;
  primaryFields: string[];
  operationalSignals: string[];
  costSignals: string[];
  riskFields: string[];
}

const SERVICE_ICONS: Record<string, typeof Database> = {
  ec2: Zap,
  s3: Database,
  rds: Database,
  lambda: Zap,
  vpc: Network,
  iam: KeyRound,
  dynamodb: Database,
  cloudfront: ShieldCheck,
};

const SERVICE_BLUEPRINTS: Record<string, ServiceBlueprint> = {
  ec2: {
    focus: "Compute inventory must expose instance identity, lifecycle state, capacity shape, network attachment, launch context, tags, utilization, and execution safety status.",
    primaryFields: ["InstanceId", "InstanceType", "State.Name", "LaunchTime", "ImageId", "IamInstanceProfile", "SecurityGroups", "SubnetId", "VpcId"],
    operationalSignals: ["cpu_p95", "network evidence", "Auto Scaling membership", "allowlist tag", "owner", "environment", "current state"],
    costSignals: ["monthly_cost_usd", "focus_row_count", "cost_source", "rightsizing savings", "stop/start schedule impact"],
    riskFields: ["termination blocked", "ASG context required", "security group context required", "human approval required"],
  },
  s3: {
    focus: "Object storage coverage must show bucket identity, location, tags, lifecycle posture, storage-class analysis, inventory/export context, and destructive-action protection.",
    primaryFields: ["BucketName", "CreationDate", "LocationConstraint", "LifecycleConfiguration", "AnalyticsConfiguration", "InventoryConfiguration", "BucketTagging"],
    operationalSignals: ["storage class analysis", "lifecycle rules", "inventory export", "tag posture", "FOCUS export bucket"],
    costSignals: ["monthly_cost_usd", "storage class transition opportunity", "object age/access pattern", "management analytics cost"],
    riskFields: ["DeleteBucket blocked", "DeleteObject blocked", "object contents not read", "lifecycle needs evidence"],
  },
  rds: {
    focus: "Database coverage must separate cost action from availability risk by showing class, engine, status, endpoint, Multi-AZ, deletion protection, backup/log posture, and utilization.",
    primaryFields: ["DBInstanceIdentifier", "DBInstanceClass", "Engine", "DBInstanceStatus", "Endpoint", "MultiAZ", "DeletionProtection", "EnabledCloudwatchLogsExports"],
    operationalSignals: ["cpu_p95", "connection evidence", "MultiAZ", "backup posture", "maintenance window", "storage encryption"],
    costSignals: ["monthly_cost_usd", "instance class downsizing", "idle stop window", "storage growth"],
    riskFields: ["DeleteDBInstance blocked", "downtime approval required", "snapshot/rollback needed", "production review required"],
  },
  lambda: {
    focus: "Serverless coverage must show function configuration, runtime, memory, timeout, role, package size, state, update status, tags, and concurrency controls.",
    primaryFields: ["FunctionName", "Runtime", "Handler", "Role", "MemorySize", "Timeout", "CodeSize", "State", "LastUpdateStatus"],
    operationalSignals: ["invocation trend", "error rate", "duration", "memory headroom", "reserved concurrency", "event source risk"],
    costSignals: ["monthly_cost_usd", "memory right-sizing", "idle function detection", "concurrency cap impact"],
    riskFields: ["DeleteFunction blocked", "RemovePermission blocked", "iam:PassRole must be scoped", "event flow review required"],
  },
  vpc: {
    focus: "Network coverage must expose VPC/subnet/security-group/routing dependency context so cost automation never breaks traffic paths.",
    primaryFields: ["VpcId", "CidrBlock", "State", "IsDefault", "SubnetIds", "RouteTables", "SecurityGroups", "InternetGateway", "NatGateway"],
    operationalSignals: ["CIDR coverage", "subnet distribution", "security group exposure", "route table dependencies", "endpoint/NAT posture"],
    costSignals: ["NAT gateway cost context", "endpoint consolidation", "unused network primitives", "tagging coverage"],
    riskFields: ["DeleteVpc blocked", "DeleteSubnet blocked", "route/security changes security-reviewed", "tagging-only executor"],
  },
  iam: {
    focus: "Identity coverage must show account posture, users, groups, attached managed policies, inline policies, access-key age, CloudTrail creator attribution, and privilege boundaries.",
    primaryFields: ["UserName", "Arn", "CreateDate", "GroupList", "AttachedManagedPolicies", "UserPolicyList", "AccessKeyAgeDays"],
    operationalSignals: ["root MFA", "root access keys", "password policy", "stale active keys", "admin policy exposure", "creator attribution"],
    costSignals: ["governance risk, not FOCUS cost", "creator accountability", "blast-radius ownership"],
    riskFields: ["iam:* blocked", "privilege escalation actions blocked", "self-granting permissions blocked", "separate read/executor roles"],
  },
  dynamodb: {
    focus: "Table coverage must show table status, billing mode, key schema, indexes, size, item count, backups, deletion protection, and throughput mode.",
    primaryFields: ["TableName", "TableStatus", "BillingModeSummary", "KeySchema", "GlobalSecondaryIndexes", "TableSizeBytes", "ItemCount", "DeletionProtectionEnabled"],
    operationalSignals: ["ACTIVE status", "on-demand/provisioned mode", "GSI count", "backup/PITR posture", "table class"],
    costSignals: ["monthly_cost_usd", "billing mode optimization", "unused provisioned capacity", "table class change"],
    riskFields: ["DeleteTable blocked", "DeleteBackup blocked", "global table changes blocked", "backup posture required"],
  },
  cloudfront: {
    focus: "CDN coverage must show distribution config, origins, cache behaviors, aliases, viewer certificate, logging, IPv6, price class, WAF, and invalidation/update safety.",
    primaryFields: ["Id", "DomainName", "Enabled", "Origins", "DefaultCacheBehavior", "Aliases", "PriceClass", "ViewerCertificate", "WebACLId"],
    operationalSignals: ["origin map", "cache behavior count", "alias coverage", "logging", "HTTP version", "WAF attachment", "IPv6"],
    costSignals: ["monthly_cost_usd", "price class", "cache hit impact", "invalidation volume"],
    riskFields: ["DeleteDistribution blocked", "ETag-aware updates required", "global traffic approval required", "WAF changes reviewed"],
  },
};

function asErrorMessage(error: unknown) {
  if (!error) return null;
  if (isApiError(error)) return error.message;
  if (error instanceof Error) return error.message;
  return "Request failed.";
}

function byResourceType(resources: ResourceItem[]) {
  return resources.reduce<Record<string, number>>((acc, resource) => {
    const type = resource.resource_type ?? "unknown";
    acc[type] = (acc[type] ?? 0) + 1;
    return acc;
  }, {});
}

function serviceResources(resources: ResourceItem[], resourceTypes: string[]) {
  return resources.filter((resource) => resource.resource_type && resourceTypes.includes(resource.resource_type));
}

function serviceNameFromResourceType(type: string) {
  if (type === "ec2_instance") return "Amazon EC2";
  if (type === "ebs_volume") return "Amazon EBS";
  if (type === "rds_instance") return "Amazon RDS";
  if (type === "dynamodb_table") return "Amazon DynamoDB";
  if (type === "lambda_function") return "AWS Lambda";
  if (type === "s3_bucket") return "Amazon S3";
  if (type === "vpc") return "Amazon VPC";
  if (type === "security_group") return "Security Groups";
  if (type === "iam_user") return "AWS IAM";
  if (type === "cloudfront_distribution") return "Amazon CloudFront";
  return type.replace(/_/g, " ");
}

function slugFromResourceType(type: string) {
  if (type.includes("ec2") || type.includes("ebs")) return type === "ebs_volume" ? "ebs" : "ec2";
  if (type.includes("rds")) return "rds";
  if (type.includes("dynamodb")) return "dynamodb";
  if (type.includes("lambda")) return "lambda";
  if (type.includes("s3")) return "s3";
  if (type.includes("vpc")) return "vpc";
  if (type.includes("security_group")) return "vpc";
  if (type.includes("iam")) return "iam";
  if (type.includes("cloudfront")) return "cloudfront";
  return type.replace(/_/g, "-");
}

function realServicesFromResources(resources: ResourceItem[]): AwsCoreServiceFactor[] {
  const types = Array.from(new Set(resources.map((resource) => resource.resource_type).filter(Boolean))) as string[];
  return types.sort().map((type) => ({
    service: serviceNameFromResourceType(type),
    slug: slugFromResourceType(type),
    resource_types: [type],
    purpose: "Live service detected from the current AWS resource inventory returned by /v1/resources.",
    inventory_status: "implemented",
    collector_actions: ["Loaded from /v1/resources"],
    read_only_policies: ["Uses configured CloudCare AWS read permissions"],
    full_access_policies: [],
    approved_executor_actions: type === "ec2_instance" ? ["ec2:StartInstances", "ec2:StopInstances"] : [],
    blocked_executor_actions: type === "lambda_function" ? ["Lambda write policy not configured"] : ["No direct mutation from this page"],
    rules: ["Counts, FOCUS rows, monthly cost, state, tags, owner, and environment are calculated from live resource data."],
    risk_notes: "This fallback is real inventory driven; metadata API is only used for richer policy descriptions.",
  }));
}

function money(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "not costed";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

const EC2_INSTANCE_SPECS: Record<string, { vcpu: number; memory_gib: number }> = {
  "t3.micro": { vcpu: 2, memory_gib: 1 },
};

function isEc2Resource(resource: ResourceItem) {
  return resource.resource_type === "ec2_instance" || resource.id.startsWith("i-");
}

function instanceTypeFor(resource: ResourceItem) {
  if (!isEc2Resource(resource)) return null;
  return resource.instance_type ?? resource.type ?? "unknown";
}

function ec2SpecFor(resource: ResourceItem) {
  const instanceType = instanceTypeFor(resource);
  const fallback = instanceType ? EC2_INSTANCE_SPECS[instanceType] : undefined;
  return {
    instanceType,
    vcpu: resource.vcpu ?? fallback?.vcpu ?? null,
    memoryGib: resource.memory_gib ?? fallback?.memory_gib ?? null,
  };
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="num max-h-[420px] overflow-auto rounded-[8px] border border-border bg-[#101820] p-3 text-[11px] leading-relaxed text-[#d9e7df]">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function getResourceValue(resource: ResourceItem, field: string): string {
  const normalized = field.toLowerCase();
  const tags = resource.tags ?? {};
  const tagMatch = Object.entries(tags).find(([key]) => key.toLowerCase() === normalized || key.toLowerCase().includes(normalized));
  if (tagMatch) return tagMatch[1];
  if (normalized.includes("state") || normalized.includes("status")) return resource.state ?? resource.status ?? "not returned";
  if (normalized.includes("region") || normalized.includes("location")) return resource.region || "not returned";
  if (normalized.includes("tag")) return Object.keys(tags).length ? `${Object.keys(tags).length} tags` : "not returned";
  if (normalized.includes("cost") || normalized.includes("monthly")) return money(resource.monthly_cost_usd);
  if (normalized.includes("focus")) return `${resource.focus_row_count ?? 0} rows / ${resource.cost_source}`;
  if (normalized.includes("owner")) return resource.owner ?? "not returned";
  if (normalized.includes("environment")) return resource.environment ?? "not returned";
  if (normalized.includes("cpu")) return Number.isFinite(resource.cpu_p95) ? `${resource.cpu_p95}% p95` : "not returned";
  if (normalized.includes("type") || normalized.includes("class") || normalized.includes("runtime")) return resource.resource_type ?? resource.type ?? "not returned";
  if (normalized.includes("id") || normalized.includes("name") || normalized.includes("bucket") || normalized.includes("table") || normalized.includes("function")) {
    return resource.id || "not returned";
  }
  return "not returned";
}

function FieldMatrix({
  service,
  resources,
  governance,
}: {
  service: AwsCoreServiceFactor;
  resources: ResourceItem[];
  governance: IAMGovernanceOverview | undefined;
}) {
  const blueprint = SERVICE_BLUEPRINTS[service.slug];
  const firstResource = resources[0];

  if (service.slug === "iam") {
    return (
      <div className="grid gap-3 lg:grid-cols-2">
        <section className="rounded-[8px] border border-border bg-background p-3">
          <h3 className="text-[12px] font-semibold uppercase text-ink-dim">Account posture returned</h3>
          <div className="mt-3 grid gap-2">
            <Metric label="Account" value={governance?.account.account_id ?? "not returned"} />
            <Metric label="Root MFA" value={String(governance?.account.root_mfa_enabled ?? "unknown")} />
            <Metric label="Root access keys" value={String(governance?.account.root_access_keys_present ?? "unknown")} />
            <Metric label="Password policy" value={String(governance?.account.password_policy_configured ?? "unknown")} />
          </div>
        </section>
        <section className="rounded-[8px] border border-border bg-background p-3">
          <h3 className="text-[12px] font-semibold uppercase text-ink-dim">IAM users returned</h3>
          <div className="mt-2 max-h-72 overflow-y-auto space-y-2">
            {(governance?.users ?? []).map((user) => (
              <div key={user.arn} className="rounded-[8px] border border-border bg-card p-2.5">
                <div className="font-medium text-foreground">{user.user_name}</div>
                <div className="num mt-1 truncate text-[10.5px] text-ink-faint">{user.arn}</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Badge variant="outline">{user.groups.length} groups</Badge>
                  <Badge variant="outline">{user.policies.length} policies</Badge>
                  <Badge variant={user.access_key_age_days !== null && user.access_key_age_days >= 90 ? "destructive" : "outline"}>
                    key age {user.access_key_age_days ?? "none"}
                  </Badge>
                </div>
              </div>
            ))}
            {!governance?.users?.length ? <p className="text-[12px] text-ink-faint">No IAM users returned.</p> : null}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <section className="rounded-[8px] border border-border bg-background p-3">
        <h3 className="text-[12px] font-semibold uppercase text-ink-dim">{service.service} data model</h3>
        <p className="mt-2 text-[12.5px] leading-relaxed text-ink-dim">{blueprint?.focus ?? service.purpose}</p>
      </section>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="rounded-[8px] border border-border bg-background p-3">
          <h3 className="text-[12px] font-semibold uppercase text-ink-dim">AWS fields to collect</h3>
          <div className="mt-2 grid gap-2">
            {(blueprint?.primaryFields ?? service.resource_types).map((field) => (
              <div key={field} className="grid grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)] gap-2 rounded-[7px] border border-border bg-card px-2.5 py-2 text-[11.5px]">
                <span className="num truncate text-ink-dim">{field}</span>
                <span className="truncate text-ink-faint">{firstResource ? getResourceValue(firstResource, field) : "not returned yet"}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[8px] border border-border bg-background p-3">
          <h3 className="text-[12px] font-semibold uppercase text-ink-dim">Current returned resource evidence</h3>
          <div className="mt-2 grid gap-2">
            <Metric label="Resources returned" value={resources.length} />
            <Metric label="Costed resources" value={`${resources.filter((resource) => resource.monthly_cost_usd !== null).length}/${resources.length}`} />
            <Metric label="FOCUS rows" value={resources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0)} />
            <Metric label="Monthly cost" value={money(resources.reduce((sum, resource) => sum + (resource.monthly_cost_usd ?? 0), 0))} />
          </div>
        </section>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <ListBlock title="Operational signals" items={blueprint?.operationalSignals ?? []} />
        <ListBlock title="Cost signals" items={blueprint?.costSignals ?? []} tone="good" />
        <ListBlock title="Risk fields" items={blueprint?.riskFields ?? service.rules} tone="bad" />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[8px] border border-border bg-card px-3 py-2.5">
      <div className="text-[10px] font-medium uppercase text-ink-faint">{label}</div>
      <div className="num mt-1 truncate text-[15px] font-semibold text-foreground">{value}</div>
    </div>
  );
}

function ListBlock({ title, items, tone = "neutral" }: { title: string; items: string[]; tone?: "neutral" | "good" | "bad" }) {
  const color = tone === "good" ? "var(--mint)" : tone === "bad" ? "var(--destructive)" : "var(--signal)";
  return (
    <section className="rounded-[8px] border border-border bg-background p-3">
      <h3 className="text-[12px] font-semibold uppercase text-ink-dim">{title}</h3>
      {items.length ? (
        <div className="mt-2 space-y-1.5">
          {items.map((item) => (
            <div key={item} className="flex gap-2 text-[12px] leading-relaxed text-ink-dim">
              <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" style={{ color }} />
              <span>{item}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-[12px] text-ink-faint">No entries returned by the API.</p>
      )}
    </section>
  );
}

function ServiceCardSignals({ service, resources }: { service: AwsCoreServiceFactor; resources: ResourceItem[] }) {
  const blueprint = SERVICE_BLUEPRINTS[service.slug];
  const returnedSignals = [
    `${resources.length} resources`,
    `${resources.filter((resource) => resource.monthly_cost_usd !== null).length} costed`,
    `${resources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0)} FOCUS rows`,
  ];
  const serviceSignals = blueprint?.operationalSignals.slice(0, 3) ?? service.resource_types.slice(0, 3);
  return (
    <div className="mt-3 grid gap-2">
      <div className="rounded-[8px] border border-border bg-card px-3 py-2">
        <div className="text-[10px] font-medium uppercase text-ink-faint">Returned now</div>
        <div className="num mt-1 text-[11.5px] text-ink-dim">{returnedSignals.join(" / ")}</div>
      </div>
      <div className="rounded-[8px] border border-border bg-card px-3 py-2">
        <div className="text-[10px] font-medium uppercase text-ink-faint">{service.service} specific checks</div>
        <div className="mt-1 text-[11.5px] text-ink-dim">{serviceSignals.join(", ")}</div>
      </div>
    </div>
  );
}

function ResourceTable({ resources }: { resources: ResourceItem[] }) {
  if (!resources.length) {
    return (
      <div className="rounded-[8px] border border-dashed border-border bg-background p-6 text-center text-[12.5px] text-ink-faint">
        No matching discovered resources returned for this service yet.
      </div>
    );
  }

  const showHardware = resources.some(isEc2Resource);

  return (
    <div className="overflow-x-auto rounded-[8px] border border-border bg-background">
      <table className="w-full min-w-[1120px] text-left text-[12px]">
        <thead className="border-b border-border bg-secondary/45 text-[10px] uppercase text-ink-faint">
          <tr>
            <th className="px-3 py-2">Resource</th>
            <th className="px-3 py-2">Type</th>
            {showHardware ? <th className="px-3 py-2">Instance type</th> : null}
            {showHardware ? <th className="px-3 py-2">RAM</th> : null}
            {showHardware ? <th className="px-3 py-2">vCPU</th> : null}
            <th className="px-3 py-2">Region</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Monthly cost</th>
            <th className="px-3 py-2">FOCUS source</th>
            <th className="px-3 py-2">Owner</th>
            <th className="px-3 py-2">Environment</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {resources.map((resource) => {
            const spec = ec2SpecFor(resource);
            return (
              <tr key={resource.id} className="align-top">
                <td className="max-w-[260px] px-3 py-2">
                  <div className="num truncate font-medium text-foreground">{resource.id}</div>
                  <div className="num mt-1 truncate text-[10.5px] text-ink-faint">{resource.focus_dataset_id ?? "no dataset id"}</div>
                </td>
                <td className="px-3 py-2 text-ink-dim">{resource.resource_type ?? resource.type}</td>
                {showHardware ? <td className="num px-3 py-2 text-ink-dim">{spec.instanceType ?? "-"}</td> : null}
                {showHardware ? <td className="num px-3 py-2 text-ink-dim">{spec.memoryGib === null ? "-" : `${spec.memoryGib} GiB`}</td> : null}
                {showHardware ? <td className="num px-3 py-2 text-ink-dim">{spec.vcpu ?? "-"}</td> : null}
                <td className="num px-3 py-2 text-ink-dim">{resource.region}</td>
                <td className="px-3 py-2">
                  <Badge variant={resource.status === "Healthy" ? "secondary" : "outline"}>{resource.status}</Badge>
                </td>
                <td className="num px-3 py-2 text-ink-dim">{money(resource.monthly_cost_usd)}</td>
                <td className="px-3 py-2 text-ink-dim">
                  <div>{resource.cost_source}</div>
                  <div className="num text-[10.5px] text-ink-faint">{resource.focus_row_count} rows</div>
                </td>
                <td className="px-3 py-2 text-ink-dim">{resource.owner ?? "unknown"}</td>
                <td className="px-3 py-2 text-ink-dim">{resource.environment}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ServiceDetailDialog({
  service,
  resources,
  governance,
  payload,
  open,
  onOpenChange,
}: {
  service: AwsCoreServiceFactor | null;
  resources: ResourceItem[];
  governance: IAMGovernanceOverview | undefined;
  payload: AwsCoreServicesExternalFactor | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [section, setSection] = useState<DetailSection>("overview");
  if (!service) return null;

  const matchedResources = serviceResources(resources, service.resource_types);
  const focusRows = matchedResources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0);
  const totalCost = matchedResources.reduce((sum, resource) => sum + (resource.monthly_cost_usd ?? 0), 0);
  const Icon = SERVICE_ICONS[service.slug] ?? Database;
  const rawDetail = {
    service,
    matched_resources: matchedResources,
    iam_governance: service.slug === "iam" ? governance ?? null : null,
    external_factor_payload: payload ?? null,
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-[1120px] overflow-hidden p-0">
        <DialogHeader className="border-b border-border bg-[linear-gradient(135deg,#10222e,#173a38_58%,#314033)] p-5 text-left text-white">
          <div className="flex items-start gap-3 pr-8">
            <span className="grid size-11 shrink-0 place-items-center rounded-[8px] border border-white/15 bg-white/10">
              <Icon className="size-5" />
            </span>
            <div className="min-w-0">
              <DialogTitle className="truncate text-xl text-white">{service.service}</DialogTitle>
              <DialogDescription className="mt-2 max-w-4xl text-[13px] leading-relaxed text-white/72">
                {service.purpose}
              </DialogDescription>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="secondary">{service.inventory_status}</Badge>
                <Badge variant="outline" className="border-white/20 text-white">{matchedResources.length} resources</Badge>
                <Badge variant="outline" className="border-white/20 text-white">{focusRows} FOCUS rows</Badge>
                <Badge variant="outline" className="border-white/20 text-white">{money(totalCost)} monthly</Badge>
              </div>
            </div>
          </div>
        </DialogHeader>

        <div className="grid max-h-[calc(92vh-148px)] min-h-[560px] grid-cols-1 overflow-hidden lg:grid-cols-[220px_1fr]">
          <aside className="border-b border-border bg-secondary/30 p-3 lg:border-b-0 lg:border-r">
            {(["overview", "aws-data", "resources", "permissions", "rules", "raw"] as DetailSection[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setSection(item)}
                className={`mb-1 flex h-9 w-full items-center justify-between rounded-[7px] px-3 text-left text-[12px] font-medium capitalize transition ${
                  section === item ? "bg-foreground text-background" : "text-ink-dim hover:bg-background"
                }`}
              >
                {item.replace("-", " ")}
                <ChevronRight className="size-3.5" />
              </button>
            ))}
          </aside>

          <main className="overflow-y-auto p-4">
            {section === "overview" && (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Metric label="Resource types" value={service.resource_types.length} />
                  <Metric label="Collector actions" value={service.collector_actions.length} />
                  <Metric label="Approved actions" value={service.approved_executor_actions.length} />
                  <Metric label="Blocked actions" value={service.blocked_executor_actions.length} />
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  <ListBlock title="Resource types returned" items={service.resource_types} />
                  <ListBlock title="Collector actions returned" items={service.collector_actions} />
                </div>
                <section className="rounded-[8px] border border-border bg-background p-3">
                  <h3 className="text-[12px] font-semibold uppercase text-ink-dim">Risk notes</h3>
                  <p className="mt-2 text-[12.5px] leading-relaxed text-ink-dim">{service.risk_notes}</p>
                </section>
                {service.slug === "iam" && governance ? (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <Metric label="IAM users" value={governance.users.length} />
                    <Metric label="Creator records" value={governance.resource_creators.length} />
                    <Metric label="Root MFA" value={String(governance.account.root_mfa_enabled ?? "unknown")} />
                    <Metric label="Password policy" value={String(governance.account.password_policy_configured ?? "unknown")} />
                  </div>
                ) : null}
              </div>
            )}

            {section === "aws-data" && (
              <FieldMatrix service={service} resources={matchedResources} governance={governance} />
            )}

            {section === "resources" && (
              <div className="space-y-4">
                <ResourceTable resources={matchedResources} />
                <JsonBlock value={matchedResources} />
              </div>
            )}

            {section === "permissions" && (
              <div className="grid gap-3 lg:grid-cols-2">
                <ListBlock title="Read-only policies" items={service.read_only_policies} />
                <ListBlock title="Full-access policies" items={service.full_access_policies} />
                <ListBlock title="Approved executor actions" items={service.approved_executor_actions} tone="good" />
                <ListBlock title="Blocked executor actions" items={service.blocked_executor_actions} tone="bad" />
                <section className="rounded-[8px] border border-border bg-background p-3 lg:col-span-2">
                  <h3 className="text-[12px] font-semibold uppercase text-ink-dim">Runtime executor boundary</h3>
                  <p className="mt-2 text-[12.5px] leading-relaxed text-ink-dim">
                    {payload?.executor_role_boundaries.allowed_pattern ?? "No executor boundary returned."}
                  </p>
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    <ListBlock title="Required gates" items={payload?.executor_role_boundaries.required_gates ?? []} tone="good" />
                    <ListBlock title="Globally excluded actions" items={payload?.executor_role_boundaries.excluded ?? []} tone="bad" />
                  </div>
                </section>
              </div>
            )}

            {section === "rules" && (
              <div className="space-y-3">
                <ListBlock title="Service rules" items={service.rules} />
                <ListBlock title="External-factor notes" items={payload?.notes ?? []} />
                {service.slug === "iam" && governance ? (
                  <section className="rounded-[8px] border border-border bg-background p-3">
                    <h3 className="text-[12px] font-semibold uppercase text-ink-dim">IAM governance errors</h3>
                    <JsonBlock value={governance.errors} />
                  </section>
                ) : null}
              </div>
            )}

            {section === "raw" && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-[12px] font-medium uppercase text-ink-dim">
                  <FileJson className="size-4" />
                  Complete dialog source data
                </div>
                <JsonBlock value={rawDetail} />
              </div>
            )}
          </main>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function AwsCoreServicesPage() {
  const [coverageFilter, setCoverageFilter] = useState<CoverageFilter>("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedService, setSelectedService] = useState<AwsCoreServiceFactor | null>(null);

  const resourcesQuery = useResources();
  const factorQuery = useQuery({
    queryKey: ["aws-core-services-external-factor"],
    queryFn: () => api.get<AwsCoreServicesExternalFactor>("/v1/external-factors/aws-core-services"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
  });
  const governanceQuery = useQuery({
    queryKey: ["aws-core-services-iam-governance"],
    queryFn: () => api.get<IAMGovernanceOverview>("/v1/governance/iam-overview"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
  });

  const resources = useMemo(() => resourcesQuery.data ?? [], [resourcesQuery.data]);
  const services = useMemo(() => {
    if (factorQuery.data?.services?.length) return factorQuery.data.services;
    return realServicesFromResources(resources);
  }, [factorQuery.data?.services, resources]);
  const counts = useMemo(() => byResourceType(resources), [resources]);
  const typeOptions = useMemo(() => Array.from(new Set(services.flatMap((service) => service.resource_types))).sort(), [services]);
  const filteredServices = useMemo(
    () =>
      services.filter((service) => {
        const query = search.trim().toLowerCase();
        const matchedResources = serviceResources(resources, service.resource_types);
        const matchesSearch =
          !query ||
          service.service.toLowerCase().includes(query) ||
          service.slug.toLowerCase().includes(query) ||
          service.purpose.toLowerCase().includes(query) ||
          service.resource_types.some((type) => type.toLowerCase().includes(query)) ||
          service.collector_actions.some((action) => action.toLowerCase().includes(query));

        if (!matchesSearch) return false;
        if (typeFilter !== "all" && !service.resource_types.includes(typeFilter)) return false;
        if (coverageFilter === "with_resources" && matchedResources.length === 0 && service.slug !== "iam") return false;
        if (coverageFilter === "implemented" && service.inventory_status !== "implemented") return false;
        if (coverageFilter === "planned" && service.inventory_status !== "planned") return false;
        return true;
      }),
    [coverageFilter, resources, search, services, typeFilter],
  );

  const focusStats = useMemo(() => {
    const totalRows = resources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0);
    const costed = resources.filter((resource) => resource.monthly_cost_usd !== null).length;
    const totalMonthly = resources.reduce((sum, resource) => sum + (resource.monthly_cost_usd ?? 0), 0);
    return {
      totalRows,
      costed,
      totalMonthly,
      source: resources.find((resource) => resource.focus_source)?.focus_source ?? "not returned",
      version: resources.find((resource) => resource.focus_version)?.focus_version ?? "not returned",
    };
  }, [resources]);

  const refreshing = factorQuery.isFetching || resourcesQuery.isFetching || governanceQuery.isFetching;
  const errorMessage =
    asErrorMessage(factorQuery.error) || asErrorMessage(resourcesQuery.error) || asErrorMessage(governanceQuery.error);

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage py-1">
        <div className="eyebrow">Live AWS coverage</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">
          AWS core services
        </h1>
        <p className="mt-2 max-w-3xl text-[12.5px] leading-relaxed text-ink-faint">
          Service metadata is loaded from the backend external-factor API. Resource counts and FOCUS cost coverage come from the
          live dashboard resource inventory.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{services.length} services returned</Badge>
          <Badge variant="outline">{resources.length} discovered resources</Badge>
          <Badge variant="outline">FOCUS {focusStats.version}</Badge>
          <Badge variant="outline">{focusStats.totalRows} FOCUS rows</Badge>
          <Badge variant="outline">{money(focusStats.totalMonthly)} monthly</Badge>
          <Badge variant="outline">{factorQuery.data?.source ?? "live inventory fallback"}</Badge>
          <Button size="sm" variant="outline" disabled={refreshing} onClick={() => {
            void factorQuery.refetch();
            void resourcesQuery.refetch();
            void governanceQuery.refetch();
          }}>
            <RefreshCw className={refreshing ? "size-3.5 animate-spin" : "size-3.5"} />
            {refreshing ? "Refreshing" : "Refresh"}
          </Button>
        </div>
      </div>

      {errorMessage ? (
        <div className="mt-4 flex items-center gap-2 rounded-[8px] border border-red-200 bg-red-50 px-4 py-3 text-[12.5px] text-red-700">
          <AlertTriangle className="size-4" />
          {errorMessage}
        </div>
      ) : null}

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.38fr)]">
        <Panel title="Service coverage" eyebrow="Click any service for full detail" delay={100}>
          <div className="mb-3 grid gap-2 xl:grid-cols-[1fr_auto_auto]">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search services, resource types, IAM actions"
                className="h-9 w-full rounded-[8px] border border-border bg-background pl-9 pr-3 text-[12px] outline-none placeholder:text-ink-faint focus:border-[var(--ring)]"
              />
            </label>
            <Select value={coverageFilter} onValueChange={(value) => setCoverageFilter(value as CoverageFilter)}>
              <SelectTrigger className="h-9 w-full text-[12px] xl:w-[170px]">
                <SelectValue placeholder="Coverage" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All coverage</SelectItem>
                <SelectItem value="with_resources">With resources</SelectItem>
                <SelectItem value="implemented">Implemented</SelectItem>
                <SelectItem value="planned">Planned</SelectItem>
              </SelectContent>
            </Select>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="h-9 w-full text-[12px] xl:w-[200px]">
                <SelectValue placeholder="Resource type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All resource types</SelectItem>
                {typeOptions.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {factorQuery.isLoading && services.length === 0 ? (
            <Skeleton className="h-[520px] w-full" />
          ) : services.length === 0 ? (
            <div className="rounded-[8px] border border-dashed border-border bg-background p-8 text-center text-[12.5px] text-ink-faint">
              No AWS services found in live inventory yet.
            </div>
          ) : (
            <div className="grid gap-3 xl:grid-cols-2">
              {filteredServices.map((service) => {
                const Icon = SERVICE_ICONS[service.slug] ?? Database;
                const matchedResources = serviceResources(resources, service.resource_types);
                const governanceError = service.slug === "iam" ? governanceQuery.data?.errors?.users : undefined;
                const discovered =
                  service.slug === "iam" && governanceQuery.data?.users ? governanceQuery.data.users.length : matchedResources.length;
                const focusRows = matchedResources.reduce((sum, resource) => sum + (resource.focus_row_count ?? 0), 0);
                const costed = matchedResources.filter((resource) => resource.monthly_cost_usd !== null).length;

                return (
                  <button
                    key={service.slug}
                    type="button"
                    onClick={() => setSelectedService(service)}
                    className="rounded-[8px] border border-border bg-background p-4 text-left transition hover:-translate-y-0.5 hover:border-[var(--signal)] hover:shadow-[0_16px_36px_rgba(16,34,46,0.08)] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="grid size-10 shrink-0 place-items-center rounded-[8px] border border-border bg-card">
                          <Icon className="size-4 text-ink-dim" />
                        </div>
                        <div className="min-w-0">
                          <h2 className="truncate text-[14px] font-semibold text-foreground">{service.service}</h2>
                          <p className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-ink-faint">{service.purpose}</p>
                        </div>
                      </div>
                      <Badge variant={governanceError ? "destructive" : service.inventory_status === "implemented" ? "secondary" : "outline"}>
                        {governanceError ? "AccessDenied" : service.inventory_status}
                      </Badge>
                    </div>

                    <div className="mt-4 grid gap-2 sm:grid-cols-2">
                      <Metric label="Discovered" value={discovered} />
                      <Metric label="FOCUS rows" value={focusRows} />
                      <Metric label="Costed" value={`${costed}/${matchedResources.length}`} />
                      <Metric label="Actions" value={`${service.collector_actions.length}/${service.approved_executor_actions.length}`} />
                    </div>

                    <ServiceCardSignals service={service} resources={matchedResources} />
                    <div className="mt-3 flex items-center justify-between text-[11px] font-medium text-ink-faint">
                      <span>Open complete service dialog</span>
                      <ChevronRight className="size-4" />
                    </div>
                  </button>
                );
              })}
              {filteredServices.length === 0 ? (
                <div className="rounded-[8px] border border-dashed border-border bg-background p-8 text-center text-[12.5px] text-ink-faint xl:col-span-2">
                  No services match the current filters.
                </div>
              ) : null}
            </div>
          )}
        </Panel>

        <div className="space-y-3">
          <Panel title="Live inventory summary" eyebrow="Resources + FOCUS" delay={120}>
            <div className="grid grid-cols-2 gap-2">
              <Metric label="Resources" value={resources.length} />
              <Metric label="Costed" value={`${focusStats.costed}/${resources.length}`} />
              <Metric label="FOCUS rows" value={focusStats.totalRows} />
              <Metric label="Monthly cost" value={money(focusStats.totalMonthly)} />
            </div>
            <div className="mt-3 rounded-[8px] border border-border bg-background p-3">
              <div className="text-[10px] font-medium uppercase text-ink-faint">Resource type counts</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {Object.entries(counts).length ? (
                  Object.entries(counts).map(([type, count]) => (
                    <Badge key={type} variant="outline" className="num">
                      {type}: {count}
                    </Badge>
                  ))
                ) : (
                  <span className="text-[12px] text-ink-faint">No resource inventory returned.</span>
                )}
              </div>
            </div>
          </Panel>

          <Panel title="Discovery role" eyebrow="Policies returned by API" delay={140}>
            <div className="space-y-2">
              {(factorQuery.data?.discovery_role_recommendations ?? []).map((policy) => (
                <div key={policy} className="flex items-center justify-between gap-3 rounded-[8px] border border-border bg-background px-3 py-2">
                  <span className="text-[12px] text-ink-dim">{policy}</span>
                  <Badge variant="outline">read</Badge>
                </div>
              ))}
              {!factorQuery.data?.discovery_role_recommendations?.length ? (
                <p className="text-[12.5px] text-ink-faint">No discovery policies returned.</p>
              ) : null}
            </div>
          </Panel>

          <Panel title="Executor boundary" eyebrow="Write controls returned by API" delay={180}>
            <p className="text-[12.5px] leading-relaxed text-ink-dim">
              {factorQuery.data?.executor_role_boundaries.allowed_pattern ?? "No executor boundary returned."}
            </p>
            <div className="mt-4 space-y-1.5">
              {(factorQuery.data?.executor_role_boundaries.required_gates ?? []).map((gate) => (
                <div key={gate} className="flex gap-2 text-[11.5px] leading-relaxed text-ink-dim">
                  <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-[var(--signal)]" />
                  <span>{gate}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Blocked actions" eyebrow="Never automatic" delay={220}>
            <div className="flex flex-wrap gap-1.5">
              {(factorQuery.data?.executor_role_boundaries.excluded ?? []).map((action) => (
                <Badge key={action} variant="destructive" className="text-[10px]">
                  <Lock className="size-3" />
                  {action}
                </Badge>
              ))}
              {!factorQuery.data?.executor_role_boundaries.excluded?.length ? (
                <span className="text-[12px] text-ink-faint">No blocked actions returned.</span>
              ) : null}
            </div>
          </Panel>
        </div>
      </div>

      <ServiceDetailDialog
        service={selectedService}
        resources={resources}
        governance={governanceQuery.data}
        payload={factorQuery.data}
        open={selectedService !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedService(null);
        }}
      />
    </div>
  );
}
