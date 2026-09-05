"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, Database, FileJson, LineChart, Server, Tags } from "lucide-react";

import { Money, formatMoneyParts } from "@/components/Money";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { deriveServiceLabel, resourceIdFromArn, type Proposal, type ResourceDetail, type ResourceStatus } from "@/lib/cloudcare-data";
import { isApiError } from "@/lib/api";
import { useResourceDetail } from "@/lib/queries";

const STATUS_COLOR: Record<ResourceStatus, string> = {
  Healthy: "var(--mint)",
  Idle: "var(--signal)",
  "Over-provisioned": "var(--ember)",
  "At-risk": "var(--destructive)",
};

const RISK_COLOR: Record<string, string> = {
  low: "var(--mint)",
  medium: "var(--signal)",
  high: "var(--ember)",
  critical: "var(--destructive)",
};

function ProposalRow({ proposal }: { proposal: Proposal }) {
  return (
    <div className="rounded-md border border-hairline p-3">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="num text-[11.5px] text-foreground">
          {deriveServiceLabel(proposal.template_id, proposal.resource_arn, proposal.resource_type)}
        </span>
        <span className="text-[11px] text-ink-faint">{proposal.action_type.replace(/_/g, " ")}</span>
        <Badge
          variant="outline"
          className="text-[10px] uppercase"
          style={{
            color: RISK_COLOR[proposal.risk_level] ?? "var(--ink-faint)",
            borderColor: `color-mix(in oklab, ${RISK_COLOR[proposal.risk_level] ?? "var(--ink-faint)"} 40%, transparent)`,
          }}
        >
          {proposal.risk_level}
        </Badge>
        <Badge variant="secondary" className="text-[10px]">
          {proposal.status.replace(/_/g, " ")}
        </Badge>
      </div>
      <p className="mb-1 text-[11.5px] text-ink-dim">
        Expected savings: <Money value={Number(proposal.expected_monthly_savings) || 0} inline usdOnly />/mo
      </p>
      <p className="text-[11px] leading-relaxed text-ink-faint">{proposal.rationale}</p>
    </div>
  );
}

function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[460px] overflow-auto rounded-md border border-hairline bg-background p-3 text-[11px] leading-relaxed text-ink-dim">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function DetailGrid({ rows }: { rows: Array<[string, unknown]> }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="rounded-md border border-hairline bg-background px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-[0.1em] text-ink-faint">{label}</div>
          <div className="num mt-1 break-words text-[12.5px] font-medium text-foreground">{valueText(value)}</div>
        </div>
      ))}
    </div>
  );
}

function firstArrayItem(value: unknown, key: string): Record<string, unknown> | null {
  if (!value || typeof value !== "object") return null;
  const list = (value as Record<string, unknown>)[key];
  if (!Array.isArray(list) || !list[0] || typeof list[0] !== "object") return null;
  return list[0] as Record<string, unknown>;
}

function nested(value: unknown, path: string[]): unknown {
  let current = value;
  for (const key of path) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

function listCount(value: unknown, key: string) {
  if (!value || typeof value !== "object") return 0;
  const list = (value as Record<string, unknown>)[key];
  return Array.isArray(list) ? list.length : 0;
}

function awsSummaryRows(detail: ResourceDetail): Array<[string, unknown]> {
  const { resource, aws_live_details } = detail;
  const resourceType = resource.resource_type;

  if (resourceType === "ec2_instance") {
    const reservation = firstArrayItem(aws_live_details.describe_instances, "Reservations");
    const instance = firstArrayItem(reservation, "Instances");
    return [
      ["Instance id", instance?.InstanceId ?? resource.id],
      ["AMI", instance?.ImageId],
      ["Instance type", instance?.InstanceType ?? resource.type],
      ["State", nested(instance, ["State", "Name"]) ?? resource.state],
      ["Launch time", instance?.LaunchTime],
      ["Architecture", instance?.Architecture],
      ["Platform", instance?.PlatformDetails],
      ["VPC", instance?.VpcId],
      ["Subnet", instance?.SubnetId],
      ["Private IP", instance?.PrivateIpAddress],
      ["Public IP", instance?.PublicIpAddress],
      ["Security groups", Array.isArray(instance?.SecurityGroups) ? instance.SecurityGroups.map((item) => (item as Record<string, unknown>).GroupId) : []],
      ["Root device", instance?.RootDeviceName],
      ["Termination protection", nested(aws_live_details.disable_api_termination, ["DisableApiTermination", "Value"])],
      ["Attached EBS volumes", listCount(aws_live_details.attached_volumes, "Volumes")],
      ["ASG records", listCount(aws_live_details.autoscaling_membership, "AutoScalingInstances")],
    ];
  }

  if (resourceType === "ebs_volume") {
    const volume = firstArrayItem(aws_live_details.describe_volumes, "Volumes");
    return [
      ["Volume id", volume?.VolumeId ?? resource.id],
      ["State", volume?.State ?? resource.state],
      ["Type", volume?.VolumeType],
      ["Size GiB", volume?.Size],
      ["Encrypted", volume?.Encrypted],
      ["IOPS", volume?.Iops],
      ["Throughput", volume?.Throughput],
      ["Snapshot", volume?.SnapshotId],
      ["AZ", volume?.AvailabilityZone],
      ["Multi attach", volume?.MultiAttachEnabled],
      ["Attachments", Array.isArray(volume?.Attachments) ? volume.Attachments.length : 0],
    ];
  }

  if (resourceType === "rds_instance") {
    const db = firstArrayItem(aws_live_details.describe_db_instances, "DBInstances");
    return [
      ["DB identifier", db?.DBInstanceIdentifier ?? resource.id],
      ["Status", db?.DBInstanceStatus ?? resource.state],
      ["Class", db?.DBInstanceClass ?? resource.type],
      ["Engine", db?.Engine],
      ["Engine version", db?.EngineVersion],
      ["Endpoint", nested(db, ["Endpoint", "Address"])],
      ["Port", nested(db, ["Endpoint", "Port"])],
      ["Allocated storage", db?.AllocatedStorage],
      ["Storage type", db?.StorageType],
      ["Storage encrypted", db?.StorageEncrypted],
      ["Public", db?.PubliclyAccessible],
      ["Multi AZ", db?.MultiAZ],
      ["Deletion protection", db?.DeletionProtection],
      ["Backup retention days", db?.BackupRetentionPeriod],
      ["Maintenance window", db?.PreferredMaintenanceWindow],
      ["Subnet group", nested(db, ["DBSubnetGroup", "DBSubnetGroupName"])],
    ];
  }

  if (resourceType === "s3_bucket") {
    return [
      ["Bucket", resource.id],
      ["Region", nested(aws_live_details.get_bucket_location, ["LocationConstraint"]) ?? "us-east-1"],
      ["Versioning", nested(aws_live_details.get_bucket_versioning, ["Status"]) ?? "not enabled"],
      ["MFA delete", nested(aws_live_details.get_bucket_versioning, ["MFADelete"])],
      ["Encryption rules", listCount(nested(aws_live_details.get_bucket_encryption, ["ServerSideEncryptionConfiguration"]), "Rules")],
      ["Policy public", nested(aws_live_details.get_bucket_policy_status, ["PolicyStatus", "IsPublic"])],
      ["Lifecycle rules", listCount(aws_live_details.get_bucket_lifecycle_configuration, "Rules")],
      ["Logging target", nested(aws_live_details.get_bucket_logging, ["LoggingEnabled", "TargetBucket"])],
    ];
  }

  if (resourceType === "lambda_function") {
    const config = (aws_live_details.get_function as Record<string, unknown> | undefined)?.Configuration as Record<string, unknown> | undefined;
    return [
      ["Function", config?.FunctionName ?? resource.id],
      ["Runtime", config?.Runtime],
      ["Handler", config?.Handler],
      ["Memory MB", config?.MemorySize],
      ["Timeout sec", config?.Timeout],
      ["Package", config?.PackageType],
      ["Role", config?.Role],
      ["Last modified", config?.LastModified],
      ["Architectures", config?.Architectures],
      ["Code size", config?.CodeSize],
      ["Event mappings", listCount(aws_live_details.event_source_mappings, "EventSourceMappings")],
      ["Reserved concurrency", nested(aws_live_details.reserved_concurrency, ["ReservedConcurrentExecutions"])],
    ];
  }

  if (resourceType === "dynamodb_table") {
    const table = (aws_live_details.describe_table as Record<string, unknown> | undefined)?.Table as Record<string, unknown> | undefined;
    return [
      ["Table", table?.TableName ?? resource.id],
      ["Status", table?.TableStatus ?? resource.state],
      ["Billing mode", nested(table, ["BillingModeSummary", "BillingMode"])],
      ["Item count", table?.ItemCount],
      ["Table size bytes", table?.TableSizeBytes],
      ["Key schema", Array.isArray(table?.KeySchema) ? table.KeySchema.map((item) => `${(item as Record<string, unknown>).AttributeName}:${(item as Record<string, unknown>).KeyType}`) : []],
      ["PITR", nested(aws_live_details.continuous_backups, ["ContinuousBackupsDescription", "PointInTimeRecoveryDescription", "PointInTimeRecoveryStatus"])],
      ["TTL", nested(aws_live_details.time_to_live, ["TimeToLiveDescription", "TimeToLiveStatus"])],
      ["GSIs", Array.isArray(table?.GlobalSecondaryIndexes) ? table.GlobalSecondaryIndexes.length : 0],
      ["Streams", table?.StreamSpecification],
    ];
  }

  if (resourceType === "vpc") {
    const vpc = firstArrayItem(aws_live_details.describe_vpcs, "Vpcs");
    return [
      ["VPC", vpc?.VpcId ?? resource.id],
      ["CIDR", vpc?.CidrBlock],
      ["State", vpc?.State],
      ["Default VPC", vpc?.IsDefault],
      ["DHCP options", vpc?.DhcpOptionsId],
      ["Owner", vpc?.OwnerId],
      ["Subnets", listCount(aws_live_details.subnets, "Subnets")],
      ["Route tables", listCount(aws_live_details.route_tables, "RouteTables")],
      ["Internet gateways", listCount(aws_live_details.internet_gateways, "InternetGateways")],
      ["Security groups", listCount(aws_live_details.security_groups, "SecurityGroups")],
      ["NAT gateways", listCount(aws_live_details.nat_gateways, "NatGateways")],
    ];
  }

  if (resourceType === "security_group") {
    const group = firstArrayItem(aws_live_details.describe_security_groups, "SecurityGroups");
    return [
      ["Group", group?.GroupId ?? resource.id],
      ["Name", group?.GroupName],
      ["Description", group?.Description],
      ["VPC", group?.VpcId],
      ["Owner", group?.OwnerId],
      ["Ingress rules", Array.isArray(group?.IpPermissions) ? group.IpPermissions.length : 0],
      ["Egress rules", Array.isArray(group?.IpPermissionsEgress) ? group.IpPermissionsEgress.length : 0],
      ["Expanded rules", listCount(aws_live_details.security_group_rules, "SecurityGroupRules")],
    ];
  }

  if (resourceType === "iam_user") {
    const user = (aws_live_details.get_user as Record<string, unknown> | undefined)?.User as Record<string, unknown> | undefined;
    return [
      ["User", user?.UserName ?? resource.id],
      ["ARN", user?.Arn],
      ["Created", user?.CreateDate],
      ["Password last used", user?.PasswordLastUsed],
      ["Attached policies", listCount(aws_live_details.attached_policies, "AttachedPolicies")],
      ["Inline policies", listCount(aws_live_details.inline_policies, "PolicyNames")],
      ["Access keys", listCount(aws_live_details.access_keys, "AccessKeyMetadata")],
      ["Groups", listCount(aws_live_details.groups, "Groups")],
      ["MFA devices", listCount(aws_live_details.mfa_devices, "MFADevices")],
    ];
  }

  return [
    ["Resource id", resource.id],
    ["Resource type", resource.resource_type ?? resource.type],
    ["Provider", resource.provider],
    ["Region", resource.region],
    ["State", resource.state],
  ];
}

export function ResourceDetailSheet({
  resourceId,
  resourceType,
  onOpenChange,
}: {
  resourceId: string | null;
  resourceType?: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const detailQuery = useResourceDetail(resourceId, resourceType);

  return (
    <Sheet open={resourceId != null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl md:max-w-3xl lg:max-w-4xl">
        {resourceId == null ? null : detailQuery.isLoading ? (
          <div className="space-y-3 pt-6">
            <Skeleton className="h-7 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="mt-4 h-[300px] w-full" />
          </div>
        ) : detailQuery.isError ? (
          <div className="pt-10 text-center">
            <p className="text-[13px] text-destructive">
              {isApiError(detailQuery.error) ? detailQuery.error.message : "Could not load this resource."}
            </p>
          </div>
        ) : detailQuery.data ? (
          <ResourceDetailBody detail={detailQuery.data} />
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function ResourceDetailBody({ detail }: { detail: ResourceDetail }) {
  const {
    resource,
    metric,
    cost_trend,
    charge_breakdown,
    focus_dataset_id,
    focus_row_count,
    related_proposals,
    raw_resource,
    aws_live_details,
    aws_live_errors,
  } = detail;
  const tagEntries = Object.entries(resource.tags ?? {});
  const liveEntries = Object.entries(aws_live_details ?? {});
  const errorEntries = Object.entries(aws_live_errors ?? {});
  const awsRows = awsSummaryRows(detail);

  return (
    <div>
      <SheetHeader>
        <SheetTitle className="num break-all">{resource.id}</SheetTitle>
        <SheetDescription>
          <span className="capitalize">{resource.resource_type?.replace(/_/g, " ") ?? resource.type}</span>
          {" - "}
          <span className="uppercase">{resource.provider ?? "-"}</span>
          {" - "}
          <span className="capitalize">{resource.environment}</span>
          {" - "}
          {resource.region}
        </SheetDescription>
      </SheetHeader>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge
          variant="outline"
          style={{ color: STATUS_COLOR[resource.status], borderColor: `color-mix(in oklab, ${STATUS_COLOR[resource.status]} 40%, transparent)` }}
        >
          {resource.status}
        </Badge>
        {resource.state && <Badge variant="outline">{resource.state}</Badge>}
        {resource.owner && <Badge variant="secondary">owner: {resource.owner}</Badge>}
        <Badge variant={liveEntries.length ? "secondary" : "outline"}>{liveEntries.length} AWS detail blocks</Badge>
        {errorEntries.length ? <Badge variant="destructive">{errorEntries.length} AWS errors</Badge> : null}
      </div>

      <Tabs defaultValue="overview" className="mt-5">
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="aws">AWS live ({liveEntries.length})</TabsTrigger>
          <TabsTrigger value="cost">Cost</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
          <TabsTrigger value="proposals">Proposals ({related_proposals.length})</TabsTrigger>
          <TabsTrigger value="tags">Tags ({tagEntries.length})</TabsTrigger>
          <TabsTrigger value="raw">Raw</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <DetailGrid
            rows={[
              ["Resource id", resource.id],
              ["Type", resource.resource_type ?? resource.type],
              ["Provider", resource.provider],
              ["Region", resource.region],
              ["Environment", resource.environment],
              ["State", resource.state],
              ["Status", resource.status],
              ["Owner", resource.owner],
              ["Monthly cost", resource.monthly_cost_usd == null ? null : formatMoneyParts(resource.monthly_cost_usd).usd],
              ["Cost source", resource.cost_source],
              ["FOCUS rows", focus_row_count],
              ["Related proposals", related_proposals.length],
            ]}
          />
          <div className="rounded-md border border-hairline bg-background p-3">
            <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              <Server className="size-3.5" />
              Service specific AWS fields
            </div>
            <DetailGrid rows={awsRows} />
          </div>
        </TabsContent>

        <TabsContent value="aws" className="mt-4 space-y-4">
          {errorEntries.length ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3">
              <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-destructive">
                <AlertTriangle className="size-3.5" />
                AWS calls with errors
              </div>
              <div className="space-y-1">
                {errorEntries.map(([key, value]) => (
                  <div key={key} className="grid gap-1 text-[11.5px] sm:grid-cols-[160px_minmax(0,1fr)]">
                    <span className="num text-destructive">{key}</span>
                    <span className="break-words text-destructive/90">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {liveEntries.length === 0 ? (
            <p className="py-6 text-center text-[12.5px] text-ink-faint">No live AWS detail was returned for this resource type.</p>
          ) : (
            liveEntries.map(([key, value]) => (
              <div key={key} className="rounded-md border border-hairline bg-background p-3">
                <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                  <Database className="size-3.5" />
                  {key.replace(/_/g, " ")}
                </div>
                <JsonBlock value={value} />
              </div>
            ))
          )}
        </TabsContent>

        <TabsContent value="cost" className="mt-4">
          {cost_trend.length === 0 ? (
            <p className="py-6 text-center text-[12.5px] text-ink-faint">No FOCUS cost rows reference this resource yet.</p>
          ) : (
            <>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={cost_trend} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="resource-cost-fill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--signal)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="var(--signal)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} tickFormatter={(d: string) => d.slice(5)} />
                    <YAxis tick={{ fontSize: 10, fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip
                      formatter={(value: number) => [formatMoneyParts(value).usd, "billed cost"]}
                      contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "var(--hairline)", background: "var(--surface)" }}
                    />
                    <Area type="monotone" dataKey="billed_cost" stroke="var(--signal)" strokeWidth={2} fill="url(#resource-cost-fill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div className="mt-4 space-y-1.5">
                <p className="eyebrow mb-1">Charge breakdown</p>
                {charge_breakdown.map((item) => (
                  <div key={`${item.charge_description}-${item.charge_category}`} className="flex items-center justify-between gap-3 text-[11.5px]">
                    <span className="text-ink-dim">
                      {item.charge_description} <span className="text-ink-faint">({item.charge_category})</span>
                    </span>
                    <span className="num shrink-0 text-foreground">
                      <Money value={item.billed_cost} inline usdOnly /> <span className="text-ink-faint">- {item.row_count}</span>
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="metrics" className="mt-4 space-y-4">
          <DetailGrid
            rows={[
              ["CPU p95", `${resource.cpu_p95.toFixed(2)}%`],
              ["CPU avg", metric?.cpu_avg == null ? null : `${metric.cpu_avg.toFixed(2)}%`],
              ["Memory p95", metric?.mem_p95 == null ? null : `${metric.mem_p95.toFixed(2)}%`],
              ["Network p95 bytes", metric?.network_p95_bytes],
              ["Samples", metric?.sample_count],
              ["Window start", metric?.window_start],
              ["Window end", metric?.window_end],
              ["FOCUS dataset", focus_dataset_id],
            ]}
          />
          <div className="rounded-md border border-hairline bg-background p-3">
            <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              <LineChart className="size-3.5" />
              Raw utilization metric
            </div>
            {metric ? <JsonBlock value={metric} /> : <p className="py-4 text-center text-[12.5px] text-ink-faint">No utilization metric has been collected for this resource.</p>}
          </div>
        </TabsContent>

        <TabsContent value="proposals" className="mt-4 space-y-2">
          {related_proposals.length === 0 ? (
            <p className="py-6 text-center text-[12.5px] text-ink-faint">No proposals reference this resource.</p>
          ) : (
            related_proposals.map((p) => <ProposalRow key={p.proposal_id} proposal={p} />)
          )}
        </TabsContent>

        <TabsContent value="tags" className="mt-4">
          {tagEntries.length === 0 ? (
            <p className="py-6 text-center text-[12.5px] text-ink-faint">No tags on this resource.</p>
          ) : (
            <div className="rounded-md border border-hairline bg-background p-3">
              <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                <Tags className="size-3.5" />
                Resource tags
              </div>
              <div className="space-y-1">
                {tagEntries.map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between gap-3 text-[11.5px]">
                    <span className="num break-all text-ink-dim">{key}</span>
                    <span className="break-all text-foreground">{value || "-"}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="raw" className="mt-4 space-y-4">
          <div className="rounded-md border border-hairline bg-background p-3">
            <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              <FileJson className="size-3.5" />
              Full resource detail response
            </div>
            <JsonBlock value={detail} />
          </div>
          <div className="rounded-md border border-hairline bg-background p-3">
            <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              <FileJson className="size-3.5" />
              Stored resource document
            </div>
            <JsonBlock value={raw_resource} />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export { resourceIdFromArn };
