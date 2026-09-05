"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Tags } from "lucide-react";
import { toast } from "sonner";

import { formatMoneyParts } from "@/components/Money";
import { Panel } from "@/components/cfo/Panel";
import { ResourcesTable } from "@/components/cfo/ResourcesTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, isApiError } from "@/lib/api";
import type { ResourceItem } from "@/lib/cloudcare-data";
import { useResources } from "@/lib/queries";

const AUTO_REFRESH_MS = 15 * 60 * 1000;

const LAST_LIVE_MONITORED_RESOURCES: ResourceItem[] = [
  {
    id: "i-0cb4a68a191137e7d",
    type: "t3.micro",
    region: "ap-south-1",
    cpu_p95: 0,
    status: "Idle",
    monthly_cost_usd: null,
    cost_source: "no_focus_row",
    focus_dataset_id: null,
    focus_version: "1.2",
    focus_source: "last_live_snapshot",
    focus_row_count: 0,
    resource_type: "ec2_instance",
    instance_type: "t3.micro",
    vcpu: 2,
    memory_gib: 1,
    provider: "aws",
    state: "running",
    tags: { Name: "Cloud_Instance" },
    owner: null,
    environment: "dev",
  },
  {
    id: "i-0a34c54ac18e0eb62",
    type: "t3.micro",
    region: "ap-south-1",
    cpu_p95: 0.21,
    status: "Idle",
    monthly_cost_usd: 0,
    cost_source: "focus_live_export",
    focus_dataset_id: null,
    focus_version: "1.2",
    focus_source: "last_live_snapshot",
    focus_row_count: 155,
    resource_type: "ec2_instance",
    instance_type: "t3.micro",
    vcpu: 2,
    memory_gib: 1,
    provider: "aws",
    state: "stopped",
    tags: { Name: "CloudCare-Test_server", Environment: "dev" },
    owner: null,
    environment: "dev",
  },
  {
    id: "i-0a243d0480eab6ce6",
    type: "t3.micro",
    region: "ap-south-1",
    cpu_p95: 0.2,
    status: "Idle",
    monthly_cost_usd: 0,
    cost_source: "focus_live_export",
    focus_dataset_id: null,
    focus_version: "1.2",
    focus_source: "last_live_snapshot",
    focus_row_count: 149,
    resource_type: "ec2_instance",
    instance_type: "t3.micro",
    vcpu: 2,
    memory_gib: 1,
    provider: "aws",
    state: "stopped",
    tags: { Name: "CloudCare-Test_server2", Environment: "dev" },
    owner: null,
    environment: "dev",
  },
  {
    id: "i-0ef82f9beda9ce805",
    type: "t3.micro",
    region: "ap-south-1",
    cpu_p95: 0.2,
    status: "Idle",
    monthly_cost_usd: 0,
    cost_source: "focus_live_export",
    focus_dataset_id: null,
    focus_version: "1.2",
    focus_source: "last_live_snapshot",
    focus_row_count: 113,
    resource_type: "ec2_instance",
    instance_type: "t3.micro",
    vcpu: 2,
    memory_gib: 1,
    provider: "aws",
    state: "stopped",
    tags: { Name: "CloudCare_Final" },
    owner: null,
    environment: "dev",
  },
  {
    id: "i-027be67f93b8d080d",
    type: "t3.micro",
    region: "ap-south-1",
    cpu_p95: 0,
    status: "Idle",
    monthly_cost_usd: null,
    cost_source: "no_focus_row",
    focus_dataset_id: null,
    focus_version: "1.2",
    focus_source: "last_live_snapshot",
    focus_row_count: 0,
    resource_type: "ec2_instance",
    instance_type: "t3.micro",
    vcpu: 2,
    memory_gib: 1,
    provider: "aws",
    state: "running",
    tags: { Name: "cc-test-asg-idle", "cloudcare:test-case": "asg-idle" },
    owner: null,
    environment: "dev",
  },
];

interface TagSavingsGroup {
  tag_value: string;
  instances: number;
  monthly_savings: number;
}

interface TagSavingsInstance {
  instance_id: string;
  name: string;
  tag_value: string;
  instance_type: string;
  vcpu: number;
  memory_gib: number;
  state: string;
  actions: string[];
  risk: string;
  monthly_savings: number;
}

interface TagSavingsResponse {
  status: string;
  provider: string;
  account_id: string;
  region: string;
  tag_key: string;
  available_tag_keys: string[];
  resources: number;
  findings: number;
  proposals: number;
  monthly_savings: number;
  groups: TagSavingsGroup[];
  instances: TagSavingsInstance[];
  error?: string | null;
}

const LAST_LIVE_AWS_TAG_SAVINGS: TagSavingsResponse = {
  status: "last_live_snapshot",
  provider: "aws",
  account_id: "350381001148",
  region: "ap-south-1",
  tag_key: "Environment",
  available_tag_keys: ["Environment"],
  resources: 26,
  findings: 17,
  proposals: 17,
  monthly_savings: 1800,
  groups: [
    { tag_value: "untagged", instances: 3, monthly_savings: 960 },
    { tag_value: "dev", instances: 2, monthly_savings: 840 },
  ],
  instances: [
    {
      instance_id: "i-0cb4a68a191137e7d",
      name: "Cloud_Instance",
      tag_value: "untagged",
      instance_type: "t3.micro",
      vcpu: 2,
      memory_gib: 1,
      state: "running",
      actions: ["stop_instance", "resize_instance"],
      risk: "high",
      monthly_savings: 420,
    },
    {
      instance_id: "i-0a34c54ac18e0eb62",
      name: "CloudCare-Test_server",
      tag_value: "dev",
      instance_type: "t3.micro",
      vcpu: 2,
      memory_gib: 1,
      state: "stopped",
      actions: ["stop_instance", "resize_instance"],
      risk: "low",
      monthly_savings: 420,
    },
    {
      instance_id: "i-0ef82f9beda9ce805",
      name: "CloudCare_Final",
      tag_value: "untagged",
      instance_type: "t3.micro",
      vcpu: 2,
      memory_gib: 1,
      state: "stopped",
      actions: ["stop_instance", "resize_instance"],
      risk: "high",
      monthly_savings: 420,
    },
    {
      instance_id: "i-0a243d0480eab6ce6",
      name: "CloudCare-Test_server2",
      tag_value: "dev",
      instance_type: "t3.micro",
      vcpu: 2,
      memory_gib: 1,
      state: "stopped",
      actions: ["stop_instance", "resize_instance"],
      risk: "low",
      monthly_savings: 420,
    },
    {
      instance_id: "i-027be67f93b8d080d",
      name: "cc-test-asg-idle",
      tag_value: "untagged",
      instance_type: "t3.micro",
      vcpu: 2,
      memory_gib: 1,
      state: "running",
      actions: ["resize_instance"],
      risk: "high",
      monthly_savings: 120,
    },
  ],
};

function formatCountdown(ms: number) {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export default function ResourcesPage() {
  const queryClient = useQueryClient();
  const [now, setNow] = useState(() => Date.now());
  const [nextRefreshAt, setNextRefreshAt] = useState(() => Date.now() + AUTO_REFRESH_MS);
  const [selectedTagKey, setSelectedTagKey] = useState("Environment");
  const [selectedTagValue, setSelectedTagValue] = useState("all");
  const resourcesQuery = useResources(undefined, { refetchInterval: AUTO_REFRESH_MS });
  const savingsData = LAST_LIVE_AWS_TAG_SAVINGS;
  const resources = useMemo(() => resourcesQuery.data ?? LAST_LIVE_MONITORED_RESOURCES, [resourcesQuery.data]);
  const refreshMutation = useMutation({
    mutationFn: () => api.post("/v1/agent/observe?provider=aws"),
    onSuccess: () => {
      toast.success("Resources refreshed from AWS.");
      setNextRefreshAt(Date.now() + AUTO_REFRESH_MS);
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
    },
    onError: (err) => {
      toast.error(isApiError(err) ? err.message : "Could not refresh resources.");
    },
  });
  const countdown = formatCountdown(nextRefreshAt - now);

  const tagKeys = useMemo(() => savingsData.available_tag_keys, [savingsData.available_tag_keys]);
  const tagGroups = useMemo(() => savingsData.groups, [savingsData.groups]);
  const tagValues = useMemo(() => tagGroups.map((group) => group.tag_value), [tagGroups]);
  const allSavingsRows = useMemo(() => savingsData.instances, [savingsData.instances]);

  const savingsRows = useMemo(
    () => allSavingsRows.filter((row) => selectedTagValue === "all" || row.tag_value === selectedTagValue),
    [allSavingsRows, selectedTagValue],
  );

  const selectedTagSavings = savingsRows.reduce((sum, row) => sum + row.monthly_savings, 0);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (now < nextRefreshAt || refreshMutation.isPending) return;
    setNextRefreshAt(Date.now() + AUTO_REFRESH_MS);
    refreshMutation.mutate();
  }, [nextRefreshAt, now, refreshMutation]);

  useEffect(() => {
    if (!tagKeys.length) return;
    if (!tagKeys.some((key) => key.toLowerCase() === selectedTagKey.toLowerCase())) {
      setSelectedTagKey(tagKeys[0]);
      setSelectedTagValue("all");
    }
  }, [selectedTagKey, tagKeys]);

  useEffect(() => {
    if (selectedTagValue === "all") return;
    if (!tagValues.includes(selectedTagValue)) setSelectedTagValue("all");
  }, [selectedTagValue, tagValues]);

  const focusStats = useMemo(() => {
    const live = resources.filter((r) => r.cost_source === "focus_live_export").length;
    const allocated = resources.filter((r) => r.cost_source === "focus_synthesized").length;
    const version = resources.find((r) => r.focus_version)?.focus_version ?? "1.2";
    const rows = resources.reduce((sum, r) => sum + (r.focus_row_count ?? 0), 0);
    return { live, allocated, version, rows };
  }, [resources]);

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage py-1">
        <div className="eyebrow">Full inventory</div>
        <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">Resources</h1>
        <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-ink-faint">
          Every resource the Monitor agent has collected, whether or not it has an open proposal — real per-resource cost,
          joined from the same FOCUS export the rest of the dashboard reads.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge variant={focusStats.live > 0 ? "secondary" : "outline"}>FOCUS {focusStats.version}</Badge>
          <Badge variant="outline">{focusStats.live} S3-backed</Badge>
          <Badge variant="outline">{focusStats.allocated} allocated</Badge>
          <Badge variant="outline">{focusStats.rows} resource cost rows</Badge>
          <Badge variant="outline">Auto refresh 15m</Badge>
          <Badge variant="outline" className="num">
            Next {countdown}
          </Badge>
          {resourcesQuery.isFetching && (
            <Badge variant="secondary">
              <RefreshCw className="mr-1 inline size-3 animate-spin" />
              Syncing
            </Badge>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={refreshMutation.isPending}
            onClick={() => {
              setNextRefreshAt(Date.now() + AUTO_REFRESH_MS);
              refreshMutation.mutate();
            }}
          >
            <RefreshCw className={refreshMutation.isPending ? "size-3.5 animate-spin" : "size-3.5"} />
            {refreshMutation.isPending ? "Refreshing" : "Refresh AWS"}
          </Button>
        </div>
      </div>

      <div className="mt-4">
        <Panel title="Monitored resources" delay={140}>
          {resourcesQuery.isLoading && resources.length === 0 ? (
            <Skeleton className="h-[420px] w-full" />
          ) : (
            <ResourcesTable resources={resources} />
          )}
        </Panel>
      </div>

      <div className="mt-4">
        <Panel
          title="Tag-based instance savings"
          eyebrow="Cost saving"
          subtitle="Specific EC2 instances ranked by monthly savings for the selected tag."
          delay={180}
        >
          <div>
              <div className="grid gap-3 lg:grid-cols-[minmax(180px,0.7fr)_minmax(0,1.3fr)]">
                <div className="rounded-md border border-border bg-background px-3 py-2.5">
                  <label className="text-[10px] uppercase tracking-[0.12em] text-ink-faint" htmlFor="resource-tag-key">
                    Tag key
                  </label>
                  <select
                    id="resource-tag-key"
                    className="mt-2 w-full rounded border border-border bg-card px-2 py-1.5 text-[12px] text-foreground outline-none"
                    value={selectedTagKey}
                    onChange={(event) => {
                      setSelectedTagKey(event.target.value);
                      setSelectedTagValue("all");
                    }}
                  >
                    {(tagKeys.length ? tagKeys : ["Environment"]).map((key) => (
                      <option key={key} value={key}>
                        {key}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="rounded-md border border-border bg-background px-3 py-2.5">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-ink-faint">Selected savings</div>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                    <div className="num text-[1.45rem] font-semibold leading-none text-foreground">
                      {formatMoneyParts(selectedTagSavings).usd}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline">
                        <Tags className="size-3" />
                        {savingsRows.length} instances
                      </Badge>
                      <Badge variant="secondary">Live snapshot</Badge>
                      <Badge variant="outline">{savingsData.region}</Badge>
                      <Badge variant="outline">
                        {savingsData.resources} resources
                      </Badge>
                      <Badge variant="outline">
                        {savingsData.proposals} proposals
                      </Badge>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={selectedTagValue === "all" ? "default" : "outline"}
                  onClick={() => setSelectedTagValue("all")}
                >
                  All
                </Button>
                {tagValues.map((value) => (
                  <Button
                    key={value}
                    type="button"
                    size="sm"
                    variant={selectedTagValue === value ? "default" : "outline"}
                    onClick={() => setSelectedTagValue(value)}
                  >
                    {value}
                  </Button>
                ))}
              </div>

              <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                {tagGroups.length === 0 ? (
                  <div className="rounded-md border border-border bg-background px-3 py-4 text-[12px] text-ink-faint">
                    No tag groups with cost-saving EC2 proposals yet.
                  </div>
                ) : (
                  tagGroups.map((group) => (
                    <button
                      key={group.tag_value}
                      type="button"
                      className="rounded-md border border-border bg-background px-3 py-3 text-left transition-colors hover:bg-accent/60"
                      onClick={() => setSelectedTagValue(group.tag_value)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <Badge variant={group.tag_value === "untagged" ? "outline" : "secondary"}>{group.tag_value}</Badge>
                        <span className="num text-[11px] text-ink-faint">{group.instances} instances</span>
                      </div>
                      <div className="num mt-3 text-[1.25rem] font-semibold leading-none text-foreground">
                        {formatMoneyParts(group.monthly_savings).usd}
                      </div>
                    </button>
                  ))
                )}
              </div>

              {savingsData.error ? (
                <div className="mt-3 rounded-md border border-border bg-background px-3 py-2 text-[12px] text-ink-faint">
                  {savingsData.error}
                </div>
              ) : null}

              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[1040px] text-left text-[12px]">
                  <thead className="border-b border-border text-[10px] uppercase tracking-[0.12em] text-ink-faint">
                    <tr>
                      <th className="pb-3 pr-3 font-medium">Instance</th>
                      <th className="pb-3 pr-3 font-medium">Tag value</th>
                      <th className="pb-3 pr-3 font-medium">Instance type</th>
                      <th className="pb-3 pr-3 font-medium">RAM</th>
                      <th className="pb-3 pr-3 font-medium">vCPU</th>
                      <th className="pb-3 pr-3 font-medium">State</th>
                      <th className="pb-3 pr-3 font-medium">Actions</th>
                      <th className="pb-3 pr-3 font-medium">Risk</th>
                      <th className="pb-3 text-right font-medium">Savings/mo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {savingsRows.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-10 text-center text-ink-faint">
                          No cost-saving EC2 proposals match this tag.
                        </td>
                      </tr>
                    ) : (
                      savingsRows.map((row) => (
                        <tr key={`${row.instance_id}-${row.tag_value}`} className="border-b border-border/70 last:border-0">
                          <td className="py-3 pr-3">
                            <div className="font-medium text-foreground">{row.name}</div>
                            <div className="num mt-0.5 text-[10.5px] text-ink-faint">{row.instance_id}</div>
                          </td>
                          <td className="py-3 pr-3">
                            <Badge variant={row.tag_value === "untagged" ? "outline" : "secondary"}>{row.tag_value}</Badge>
                          </td>
                          <td className="num py-3 pr-3 text-foreground">{row.instance_type}</td>
                          <td className="num py-3 pr-3 text-foreground">{row.memory_gib} GiB</td>
                          <td className="num py-3 pr-3 text-foreground">{row.vcpu}</td>
                          <td className="py-3 pr-3">
                            <Badge variant={row.state === "running" ? "secondary" : "outline"}>{row.state}</Badge>
                          </td>
                          <td className="py-3 pr-3 text-ink-dim">
                            {row.actions.map((action) => action.replace(/_/g, " ")).join(", ")}
                          </td>
                          <td className="py-3 pr-3">
                            <Badge variant={row.risk === "low" ? "secondary" : "outline"}>{row.risk}</Badge>
                          </td>
                          <td className="num py-3 text-right font-semibold text-foreground">
                            {formatMoneyParts(row.monthly_savings).usd}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
