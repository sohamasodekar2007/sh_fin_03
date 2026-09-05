"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, Clipboard, KeyRound, RefreshCw, Save, ShieldCheck, XCircle } from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, isApiError } from "@/lib/api";
import type { ChatMcpCheckResponse, ChatMcpSetupResponse, ChatMcpTool } from "@/lib/cloudcare-data";
import { useChatMcpSetup } from "@/lib/queries";

const DRAFT_STORAGE_KEY = "cloudcare_chat_mcp_setup_draft";
const ENV_DRAFT_STORAGE_KEY = "cloudcare_chat_mcp_runtime_settings_draft";
const LOCAL_ENV_KEYS = [
  "APP_ENV",
  "APP_BASE_URL",
  "CORS_ORIGINS",
  "MONGODB_URI",
  "MONGODB_DB_NAME",
  "OPENAI_API_KEY",
  "OPENAI_BASE_URL",
  "OPENAI_MODEL",
  "CHATBOT_MCP_ENABLED",
] as const;
type LocalEnvKey = (typeof LOCAL_ENV_KEYS)[number];
type LocalEnvValues = Record<LocalEnvKey, string>;

const DEFAULT_TOOLS: ChatMcpTool[] = [
  {
    name: "get_latest_findings",
    description: "Get the latest tenant-scoped AWS analyzer findings.",
    inputSchema: { type: "object", properties: { provider: { type: "string", enum: ["aws"] } } },
  },
  {
    name: "get_proposal_details",
    description: "Read details for one tenant-scoped optimization proposal.",
    inputSchema: { type: "object", properties: { proposal_id: { type: "string" } } },
  },
  {
    name: "get_cost_summary",
    description: "Summarize recent tenant-scoped AWS FOCUS cost data.",
    inputSchema: { type: "object", properties: { period_days: { type: "integer" } } },
  },
  {
    name: "trigger_monitor_agent",
    description: "Trigger the monitor agent for a tenant-scoped AWS sync.",
    inputSchema: { type: "object", properties: { provider: { type: "string", enum: ["aws"] } } },
  },
  {
    name: "approve_proposal",
    description: "Return an approval card only; does not execute directly.",
    inputSchema: { type: "object", properties: { proposal_id: { type: "string" } } },
  },
];

function formatDate(value?: string | null) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Never";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function apiErrorMessage(error: unknown) {
  if (isApiError(error)) {
    if (error.status === 0) return `Network/CORS: ${error.message}`;
    return `API ${error.status}: ${error.message}`;
  }
  if (error instanceof Error) return error.message;
  return "Could not reach MCP setup API.";
}

function loadDraft() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as { clientName?: string; instructions?: string; enabled?: boolean; auditEnabled?: boolean; allowedTools?: string[] }) : null;
  } catch {
    return null;
  }
}

function saveDraft(draft: {
  clientName: string;
  instructions: string;
  enabled: boolean;
  auditEnabled: boolean;
  allowedTools: string[];
}) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
  } catch {
    /* local storage unavailable */
  }
}

function defaultEnvValues(): LocalEnvValues {
  return {
    APP_ENV: "development",
    APP_BASE_URL: "http://localhost:3002",
    CORS_ORIGINS: "http://localhost:3000,http://localhost:3002",
    MONGODB_URI: "",
    MONGODB_DB_NAME: "cloudcare",
    OPENAI_API_KEY: "",
    OPENAI_BASE_URL: "https://api.kineticrouter.com/v1",
    OPENAI_MODEL: "gpt-5.6-sol",
    CHATBOT_MCP_ENABLED: "true",
  };
}

function loadEnvDraft(): LocalEnvValues {
  if (typeof window === "undefined") return defaultEnvValues();
  try {
    const raw = window.localStorage.getItem(ENV_DRAFT_STORAGE_KEY);
    return { ...defaultEnvValues(), ...(raw ? JSON.parse(raw) : {}) };
  } catch {
    return defaultEnvValues();
  }
}

function saveEnvDraft(values: LocalEnvValues) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ENV_DRAFT_STORAGE_KEY, JSON.stringify(values));
  } catch {
    /* local storage unavailable */
  }
}

interface LocalEnvResponse {
  tenant_id: string;
  storage: string;
  collection: string;
  bootstrap_note: string;
  allowed_keys: string[];
  saved_keys?: string[];
  values: Record<string, string>;
  configured: Record<string, boolean>;
  updated_at: string | null;
  updated_by: string | null;
}

function statusBadge(ok: boolean, label: string) {
  return (
    <Badge
      variant="outline"
      className="gap-1.5 whitespace-nowrap text-[11px]"
      style={{ borderColor: ok ? "color-mix(in oklab, var(--mint) 42%, transparent)" : "color-mix(in oklab, var(--destructive) 34%, transparent)" }}
    >
      {ok ? <CheckCircle2 className="size-3.5 text-[var(--mint)]" /> : <XCircle className="size-3.5 text-destructive" />}
      {label}
    </Badge>
  );
}

export default function ChatbotMcpPage() {
  const queryClient = useQueryClient();
  const setupQuery = useChatMcpSetup();
  const data = setupQuery.data;
  const [clientName, setClientName] = useState("CloudCare Chatbot MCP");
  const [instructions, setInstructions] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [auditEnabled, setAuditEnabled] = useState(true);
  const [allowedTools, setAllowedTools] = useState<string[]>([]);
  const [tokenLabel, setTokenLabel] = useState("Dashboard chatbot token");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<ChatMcpCheckResponse | null>(null);
  const [envValues, setEnvValues] = useState<LocalEnvValues>(() => defaultEnvValues());
  const [envStatus, setEnvStatus] = useState<LocalEnvResponse | null>(null);

  useEffect(() => {
    const draft = loadDraft();
    if (!data && draft) {
      setClientName(draft.clientName || "CloudCare Chatbot MCP");
      setInstructions(draft.instructions || "");
      setEnabled(draft.enabled ?? true);
      setAuditEnabled(draft.auditEnabled ?? true);
      setAllowedTools(draft.allowedTools?.length ? draft.allowedTools : DEFAULT_TOOLS.map((tool) => tool.name));
      return;
    }
    if (!data) {
      setAllowedTools(DEFAULT_TOOLS.map((tool) => tool.name));
      setInstructions(
        "CloudCareAI is AWS-only. It may inspect tenant-scoped AWS cost, proposal, finding, CloudWatch/CloudTrail, and resource data. Non-AWS providers and cross-cloud operations are denied. Execution approvals must stay explicit and user-confirmed.",
      );
      return;
    }
    setClientName(data.setup.client_name);
    setInstructions(data.setup.instructions);
    setEnabled(data.setup.enabled);
    setAuditEnabled(data.setup.audit_enabled);
    setAllowedTools(data.setup.allowed_tools);
  }, [data]);

  useEffect(() => {
    const draft = loadEnvDraft();
    setEnvValues(draft);
    api
      .get<LocalEnvResponse>("/v1/chat/mcp/setup/runtime-settings")
      .then((result) => {
        setEnvStatus(result);
        setEnvValues((current) => ({
          ...current,
          APP_ENV: result.values.APP_ENV || current.APP_ENV,
          APP_BASE_URL: result.values.APP_BASE_URL || current.APP_BASE_URL,
          CORS_ORIGINS: result.values.CORS_ORIGINS || current.CORS_ORIGINS,
          MONGODB_DB_NAME: result.values.MONGODB_DB_NAME || current.MONGODB_DB_NAME,
          OPENAI_BASE_URL: result.values.OPENAI_BASE_URL || current.OPENAI_BASE_URL,
          OPENAI_MODEL: result.values.OPENAI_MODEL || current.OPENAI_MODEL,
          CHATBOT_MCP_ENABLED: result.values.CHATBOT_MCP_ENABLED || current.CHATBOT_MCP_ENABLED,
        }));
      })
      .catch(() => {
        setEnvStatus(null);
      });
  }, []);

  useEffect(() => {
    saveDraft({ clientName, instructions, enabled, auditEnabled, allowedTools });
  }, [clientName, instructions, enabled, auditEnabled, allowedTools]);

  useEffect(() => {
    saveEnvDraft(envValues);
  }, [envValues]);

  const viewData = data ?? {
    setup: {
      tenant_id: "local-draft",
      enabled,
      client_name: clientName,
      allowed_tools: allowedTools.length ? allowedTools : DEFAULT_TOOLS.map((tool) => tool.name),
      instructions,
      audit_enabled: auditEnabled,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      configured_by: null,
    },
    available_tools: DEFAULT_TOOLS,
    tokens: [],
    audit: [],
    status: {
      mcp_enabled: false,
      env_token_configured: false,
      dashboard_tokens: 0,
      mongo_audit_events: 0,
      model_configured: false,
      model: "backend not connected",
      model_base_url: "backend not connected",
      allowed_tool_count: allowedTools.length,
      chatbot_only_scope: true,
    },
  };

  const allowedToolSet = useMemo(() => new Set(allowedTools), [allowedTools]);

  const saveSetup = useMutation({
    mutationFn: () =>
      api.post<ChatMcpSetupResponse>("/v1/chat/mcp/setup", {
        enabled,
        client_name: clientName,
        allowed_tools: allowedTools,
        instructions,
        audit_enabled: auditEnabled,
      }),
    onSuccess: () => {
      setNewToken(null);
      void queryClient.invalidateQueries({ queryKey: ["chat-mcp-setup"] });
    },
  });

  const createToken = useMutation({
    mutationFn: () => api.post<ChatMcpSetupResponse>("/v1/chat/mcp/setup/token", { label: tokenLabel }),
    onSuccess: (result) => {
      setNewToken(result.token ?? null);
      void queryClient.invalidateQueries({ queryKey: ["chat-mcp-setup"] });
    },
  });

  const runCheck = useMutation({
    mutationFn: () => api.post<ChatMcpCheckResponse>("/v1/chat/mcp/setup/check", { run_model_probe: true }),
    onSuccess: (result) => {
      setCheckResult(result);
      void queryClient.invalidateQueries({ queryKey: ["chat-mcp-setup"] });
    },
  });

  const saveLocalEnv = useMutation({
    mutationFn: () => api.post<LocalEnvResponse>("/v1/chat/mcp/setup/runtime-settings", { values: envValues }),
    onSuccess: (result) => {
      setEnvStatus(result);
    },
  });

  function toggleTool(name: string) {
    setAllowedTools((current) => (current.includes(name) ? current.filter((tool) => tool !== name) : [...current, name].sort()));
  }

  function updateEnvValue(key: LocalEnvKey, value: string) {
    setEnvValues((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="mx-auto w-full max-w-[1560px]">
      <div className="stage flex flex-wrap items-end justify-between gap-3 py-1">
        <div>
          <div className="eyebrow">Chatbot MCP ecosystem</div>
          <h1 className="mt-1 text-[clamp(1.5rem,2.6vw,2.1rem)] font-bold leading-[1.02] text-foreground">Frontend-managed AI tool gateway</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data && statusBadge(data.status.mcp_enabled, data.status.mcp_enabled ? "MCP live" : "MCP off")}
          {data && statusBadge(data.status.model_configured, data.status.model_configured ? "AI key ready" : "AI key missing")}
          <Button size="sm" variant="outline" onClick={() => void setupQuery.refetch()} disabled={setupQuery.isFetching}>
            <RefreshCw className={setupQuery.isFetching ? "size-3.5 animate-spin" : "size-3.5"} />
            Refresh
          </Button>
        </div>
      </div>

      {setupQuery.isLoading ? (
        <Skeleton className="mt-4 h-[520px] w-full" />
      ) : (
        <div className="mt-4 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
          {setupQuery.isError && (
            <div className="xl:col-span-2 rounded border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              <div className="font-semibold">Backend setup API is not connected yet. You can still fill this page and save a local draft.</div>
              <div className="mt-1 text-xs">{apiErrorMessage(setupQuery.error)}</div>
              <div className="mt-2 text-xs text-ink-faint">
                To persist in MongoDB, start/restart backend on port 8007 and then click Save setup again.
              </div>
            </div>
          )}
          <Panel title="Mongo runtime setup" subtitle="Saved in MongoDB for this CloudCare tenant and used by the MCP readiness check." delay={100}>
            <div className="grid gap-3 lg:grid-cols-2">
              {LOCAL_ENV_KEYS.map((key) => (
                <label key={key} className="space-y-1.5">
                  <span className="eyebrow">{key}</span>
                  <Input
                    type={key.includes("KEY") || key.includes("URI") ? "password" : "text"}
                    value={envValues[key]}
                    placeholder={envStatus?.values[key] || ""}
                    onChange={(event) => updateEnvValue(key, event.target.value)}
                  />
                  {envStatus?.configured[key] && (
                    <span className="block text-[11px] text-ink-faint">MongoDB saved value: {envStatus.values[key]}</span>
                  )}
                </label>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button onClick={() => saveLocalEnv.mutate()} disabled={saveLocalEnv.isPending}>
                <Save className="size-4" />
                {saveLocalEnv.isPending ? "Saving to MongoDB" : "Save to MongoDB"}
              </Button>
              {envStatus?.collection && <span className="text-xs text-ink-faint">{envStatus.collection}</span>}
              {saveLocalEnv.isSuccess && <span className="text-xs text-[var(--mint)]">Saved in MongoDB.</span>}
              {saveLocalEnv.isError && <span className="text-xs text-destructive">{apiErrorMessage(saveLocalEnv.error)}</span>}
            </div>
            <div className="mt-2 text-xs text-ink-faint">
              {envStatus?.bootstrap_note || "Backend needs a bootstrap MongoDB connection before it can read settings from MongoDB."}
            </div>
          </Panel>

          <Panel title="Setup policy" subtitle="Saved in MongoDB and enforced before any chatbot MCP tool call." delay={120}>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1.5">
                <span className="eyebrow">Client name</span>
                <Input value={clientName} onChange={(event) => setClientName(event.target.value)} />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex items-center justify-between rounded border bg-secondary/20 px-3 py-2">
                  <span className="text-sm font-medium">Enabled</span>
                  <Switch checked={enabled} onCheckedChange={setEnabled} />
                </label>
                <label className="flex items-center justify-between rounded border bg-secondary/20 px-3 py-2">
                  <span className="text-sm font-medium">Audit</span>
                  <Switch checked={auditEnabled} onCheckedChange={setAuditEnabled} />
                </label>
              </div>
            </div>

            <label className="mt-3 block space-y-1.5">
              <span className="eyebrow">Word-to-word chatbot instruction</span>
              <Textarea className="min-h-[132px]" value={instructions} onChange={(event) => setInstructions(event.target.value)} />
            </label>

            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div>
                  <div className="eyebrow">Allowed tools</div>
                  <div className="text-xs text-ink-faint">Only selected tools are returned to MCP clients and executable by token.</div>
                </div>
                <Badge variant="outline" className="text-[11px]">
                  {allowedTools.length}/{viewData.available_tools.length}
                </Badge>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                {viewData.available_tools.map((tool) => (
                  <label key={tool.name} className="flex min-h-[74px] gap-3 rounded border bg-secondary/20 p-3">
                    <Checkbox checked={allowedToolSet.has(tool.name)} onCheckedChange={() => toggleTool(tool.name)} />
                    <span>
                      <span className="block text-sm font-semibold text-foreground">{tool.name}</span>
                      <span className="line-clamp-2 text-xs text-ink-faint">{tool.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button onClick={() => saveSetup.mutate()} disabled={saveSetup.isPending || allowedTools.length === 0}>
                <Save className="size-4" />
                {saveSetup.isPending ? "Saving" : "Save setup"}
              </Button>
              {saveSetup.isError && <span className="text-xs text-destructive">{apiErrorMessage(saveSetup.error)}</span>}
            </div>
          </Panel>

          <div className="grid gap-4">
            <Panel title="Chatbot token" subtitle="Generated once, stored only as a hash in MongoDB." delay={160}>
              <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                <Input value={tokenLabel} onChange={(event) => setTokenLabel(event.target.value)} />
                <Button variant="outline" onClick={() => createToken.mutate()} disabled={createToken.isPending}>
                  <KeyRound className="size-4" />
                  Generate
                </Button>
              </div>
              {newToken && (
                <div className="mt-3 rounded border border-[color-mix(in_oklab,var(--mint)_34%,transparent)] bg-secondary/20 p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-foreground">Copy now. This token will not be shown again.</span>
                    <Button size="sm" variant="outline" onClick={() => void navigator.clipboard.writeText(newToken)}>
                      <Clipboard className="size-3.5" />
                      Copy
                    </Button>
                  </div>
                  <code className="block break-all rounded bg-background px-2 py-2 text-xs">{newToken}</code>
                </div>
              )}
              {createToken.isError && <div className="mt-3 rounded border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">{apiErrorMessage(createToken.error)}</div>}
              <div className="mt-3 grid gap-2">
                {viewData.tokens.map((token) => (
                  <div key={token.token_id} className="rounded border bg-secondary/20 px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{token.label}</span>
                      <span className="text-xs text-ink-faint">{formatDate(token.created_at)}</span>
                    </div>
                    <div className="mt-1 text-xs text-ink-faint">Last used: {formatDate(token.last_used_at)}</div>
                  </div>
                ))}
                {viewData.tokens.length === 0 && <div className="rounded border bg-secondary/20 px-3 py-3 text-sm text-ink-faint">No dashboard tokens yet.</div>}
              </div>
            </Panel>

            <Panel title="Readiness check" subtitle={`Model ${viewData.status.model} via ${viewData.status.model_base_url}`} delay={180}>
              <div className="grid gap-2 sm:grid-cols-3">
                <div className="rounded border bg-secondary/20 p-3">
                  <ShieldCheck className="mb-2 size-4 text-[var(--signal)]" />
                  <div className="num text-xl font-semibold">{allowedTools.length || viewData.status.allowed_tool_count}</div>
                  <div className="eyebrow mt-1">Allowed tools</div>
                </div>
                <div className="rounded border bg-secondary/20 p-3">
                  <KeyRound className="mb-2 size-4 text-[var(--signal)]" />
                  <div className="num text-xl font-semibold">{viewData.status.dashboard_tokens}</div>
                  <div className="eyebrow mt-1">Tokens</div>
                </div>
                <div className="rounded border bg-secondary/20 p-3">
                  <Bot className="mb-2 size-4 text-[var(--signal)]" />
                  <div className="num text-xl font-semibold">{viewData.status.mongo_audit_events}</div>
                  <div className="eyebrow mt-1">Audit events</div>
                </div>
              </div>
              <Button className="mt-3" variant="outline" onClick={() => runCheck.mutate()} disabled={runCheck.isPending}>
                <RefreshCw className={runCheck.isPending ? "size-4 animate-spin" : "size-4"} />
                Run AI check
              </Button>
              {runCheck.isError && <div className="mt-3 rounded border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">{apiErrorMessage(runCheck.error)}</div>}
              {checkResult && (
                <div className="mt-3 space-y-2">
                  {checkResult.checks.map((check) => (
                    <div key={check.key} className="flex gap-2 rounded border bg-secondary/20 px-3 py-2 text-sm">
                      {check.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[var(--mint)]" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />}
                      <span>
                        <span className="block font-medium">{check.key.replace(/_/g, " ")}</span>
                        <span className="text-xs text-ink-faint">{check.detail}</span>
                      </span>
                    </div>
                  ))}
                  {checkResult.ai_review && (
                    <div className="rounded border bg-secondary/20 px-3 py-2 text-sm">
                      <div className="font-semibold">{checkResult.ai_review.summary}</div>
                      <div className="mt-1 text-xs text-ink-faint">{checkResult.ai_review.next_actions.join(" ")}</div>
                    </div>
                  )}
                </div>
              )}
            </Panel>
          </div>

          <Panel title="MCP audit trail" subtitle="Recent MongoDB audit events from setup and chatbot tool calls." delay={220}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="border-b text-xs uppercase tracking-[0.08em] text-ink-faint">
                  <tr>
                    <th className="px-2 py-2">Time</th>
                    <th className="px-2 py-2">Method</th>
                    <th className="px-2 py-2">Tool</th>
                    <th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {viewData.audit.map((event) => (
                    <tr key={`${event.created_at}-${event.method}-${event.tool_name ?? "setup"}`} className="border-b last:border-0">
                      <td className="px-2 py-2 text-ink-faint">{formatDate(event.created_at)}</td>
                      <td className="px-2 py-2 font-medium">{event.method}</td>
                      <td className="px-2 py-2">{event.tool_name ?? "-"}</td>
                      <td className="px-2 py-2">{event.ok ? "ok" : "failed"}</td>
                      <td className="px-2 py-2 text-destructive">{event.error ?? ""}</td>
                    </tr>
                  ))}
                  {viewData.audit.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-2 py-6 text-center text-sm text-ink-faint">
                        No MongoDB audit events yet. Save setup and call MCP after backend is connected.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
