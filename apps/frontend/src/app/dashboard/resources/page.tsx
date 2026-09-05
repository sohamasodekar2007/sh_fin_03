"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Panel } from "@/components/cfo/Panel";
import { ResourcesTable } from "@/components/cfo/ResourcesTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, isApiError } from "@/lib/api";
import { useResources } from "@/lib/queries";

const AUTO_REFRESH_MS = 15 * 60 * 1000;

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
  const resourcesQuery = useResources(undefined, { refetchInterval: AUTO_REFRESH_MS });
  const resources = useMemo(() => resourcesQuery.data ?? [], [resourcesQuery.data]);
  const refreshMutation = useMutation({
    mutationFn: () => api.post("/v1/agent/observe?provider=aws"),
    onSuccess: () => {
      toast.success("Resources refreshed from AWS.");
      setNextRefreshAt(Date.now() + AUTO_REFRESH_MS);
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      queryClient.invalidateQueries({ queryKey: ["agent-command-latest"] });
      queryClient.invalidateQueries({ queryKey: ["agent-activity"] });
    },
    onError: (err) => {
      toast.error(isApiError(err) ? err.message : "Could not refresh resources.");
    },
  });
  const countdown = formatCountdown(nextRefreshAt - now);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (now < nextRefreshAt || refreshMutation.isPending) return;
    setNextRefreshAt(Date.now() + AUTO_REFRESH_MS);
    refreshMutation.mutate();
  }, [nextRefreshAt, now, refreshMutation]);

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
          {resourcesQuery.isLoading ? (
            <Skeleton className="h-[420px] w-full" />
          ) : (
            <ResourcesTable resources={resources} />
          )}
        </Panel>
      </div>
    </div>
  );
}
