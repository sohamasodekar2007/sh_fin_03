"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  Cpu,
  Loader2,
  MessageSquareText,
  Radar,
  Send,
  Sparkles,
  TerminalSquare,
} from "lucide-react";

import { ApprovalCardView } from "@/components/chat/cards/ApprovalCardView";
import { CostSummaryCardView } from "@/components/chat/cards/CostSummaryCardView";
import { FindingCardView } from "@/components/chat/cards/FindingCardView";
import { RecommendationCardView } from "@/components/chat/cards/RecommendationCardView";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, isApiError } from "@/lib/api";
import type { ChatCard, ChatMessageResponse, ChatSessionCreateResponse } from "@/lib/cloudcare-data";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  cards: ChatCard[];
  toolCalls: string[];
}

type ChatMode = "existing" | "new";

interface WorkloadForm {
  company_size: "startup" | "smb" | "mid_market" | "enterprise";
  monthly_budget: number;
  current_storage_platform: string;
  workload_type: string;
  compliance_needs: string[];
  growth_expectation: "flat" | "moderate" | "high";
}

const EXISTING_PROMPTS = [
  {
    title: "War room",
    text: "Find the highest-impact waste, explain the evidence, and rank the next three actions.",
    icon: Radar,
  },
  {
    title: "Approval queue",
    text: "Show every proposal waiting on approval and explain which one is safest to approve first.",
    icon: CheckCircle2,
  },
  {
    title: "Spend narrative",
    text: "Summarize my current spend like a CFO briefing, with top services and risk notes.",
    icon: ClipboardList,
  },
  {
    title: "Fresh scan",
    text: "Run a fresh AWS monitor scan and tell me what changed.",
    icon: Cpu,
  },
] as const;

const NEW_WORKLOAD_PROMPTS = [
  "Design the lowest-risk AWS architecture for this workload and explain the tradeoffs.",
  "Compare pay-as-you-go against committed capacity for this workload.",
  "Give me the board-ready recommendation with cost, compliance, and operating risk.",
] as const;

const DEFAULT_FORM: WorkloadForm = {
  company_size: "smb",
  monthly_budget: 2500,
  current_storage_platform: "S3 data lake with hourly Parquet exports",
  workload_type: "Cloud cost analytics and automated optimization",
  compliance_needs: ["SOC2", "least privilege", "audit trail"],
  growth_expectation: "moderate",
};

function CardRenderer({ card, onDecided }: { card: ChatCard; onDecided: () => void }) {
  switch (card.type) {
    case "approval_card":
      return <ApprovalCardView card={card} onDecided={onDecided} />;
    case "finding_card":
      return <FindingCardView card={card} />;
    case "cost_summary_card":
      return <CostSummaryCardView card={card} />;
    case "recommendation_card":
      return <RecommendationCardView card={card} />;
    default:
      return null;
  }
}

function toolLabel(name: string) {
  return name.replace(/_/g, " ");
}

function WelcomeMessage() {
  return (
    <div className="rounded-md border border-hairline bg-surface-raised p-4">
      <div className="flex items-center gap-2">
        <Bot className="size-4 text-signal" />
        <span className="text-[13px] font-semibold text-foreground">CloudCareAI command layer</span>
      </div>
      <p className="mt-2 text-[12.5px] leading-relaxed text-ink-faint">
        Ask for AWS spend, findings, approval risk, a fresh AWS scan, or a new AWS workload design. Answers stay tied to
        CloudCare tools and approval-gated actions.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {["Observe", "Decide", "Approve"].map((step) => (
          <div key={step} className="rounded-md border border-border/70 bg-surface px-3 py-2">
            <div className="eyebrow">{step}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ message, onDecided }: { message: DisplayMessage; onDecided: () => void }) {
  const assistant = message.role === "assistant";
  return (
    <div className={`flex ${assistant ? "justify-start" : "justify-end"}`}>
      <div
        className={`max-w-[92%] rounded-lg px-3.5 py-2.5 text-[13px] leading-relaxed sm:max-w-[82%] ${
          assistant ? "border border-border bg-surface-raised text-foreground" : "bg-signal text-[var(--control-on-fg)]"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.toolCalls.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.toolCalls.map((call) => (
              <span key={call} className="rounded-md border border-border/70 bg-surface px-2 py-1 text-[10.5px] text-ink-dim">
                <TerminalSquare className="mr-1 inline size-3" />
                {toolLabel(call)}
              </span>
            ))}
          </div>
        )}
        {message.cards.map((card, index) => (
          <CardRenderer key={index} card={card} onDecided={onDecided} />
        ))}
      </div>
    </div>
  );
}

function ModeButton({
  active,
  label,
  sublabel,
  icon: Icon,
  onClick,
}: {
  active: boolean;
  label: string;
  sublabel: string;
  icon: typeof Bot;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border p-3 text-left transition-colors"
      style={{
        borderColor: active ? "var(--signal)" : "var(--border)",
        background: active ? "color-mix(in oklab, var(--signal) 9%, var(--surface))" : "var(--surface-raised)",
      }}
    >
      <div className="flex items-center gap-2">
        <Icon className="size-4 text-signal" />
        <span className="text-[12.5px] font-semibold text-foreground">{label}</span>
      </div>
      <p className="mt-1 text-[11.5px] leading-snug text-ink-faint">{sublabel}</p>
    </button>
  );
}

export function ChatWindow() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<ChatMode>("existing");
  const [sending, setSending] = useState(false);
  const [form, setForm] = useState<WorkloadForm>(DEFAULT_FORM);
  const listRef = useRef<HTMLDivElement | null>(null);

  const promptPack = mode === "existing" ? EXISTING_PROMPTS : NEW_WORKLOAD_PROMPTS.map((text) => ({ title: "Design", text, icon: BrainCircuit }));
  const canSend = Boolean(sessionId && !sending && input.trim());
  const toolCount = useMemo(() => messages.reduce((sum, message) => sum + message.toolCalls.length, 0), [messages]);

  useEffect(() => {
    api
      .post<ChatSessionCreateResponse>("/v1/chat/session")
      .then((res) => setSessionId(res.session_id))
      .catch((err) => setSessionError(isApiError(err) ? err.message : "Could not start a chat session."));
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || !sessionId || sending) return;

    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: trimmed, cards: [], toolCalls: [] }]);
    setInput("");
    setSending(true);

    try {
      const res = await api.post<ChatMessageResponse>("/v1/chat/message", {
        session_id: sessionId,
        mode,
        content: trimmed,
        form_data: mode === "new" ? form : undefined,
      });
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.content,
          cards: res.cards,
          toolCalls: res.tool_calls_made,
        },
      ]);
    } catch (err) {
      const message = isApiError(err) ? err.message : "Something went wrong reaching CloudCareAI.";
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "assistant", content: message, cards: [], toolCalls: [] }]);
    } finally {
      setSending(false);
    }
  }

  function updateForm<K extends keyof WorkloadForm>(key: K, value: WorkloadForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  return (
    <section className="panel hairline-top grid min-h-[680px] overflow-hidden xl:grid-cols-[292px_minmax(0,1fr)]">
      <aside className="border-b border-hairline bg-surface px-4 py-4 xl:border-b-0 xl:border-r">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-md bg-signal text-[var(--control-on-fg)]">
            <Sparkles className="size-4" />
          </span>
          <div>
            <div className="text-[13px] font-semibold text-foreground">Mission control</div>
            <div className="num text-[10.5px] text-ink-faint">{sessionId ? sessionId.slice(0, 8) : "starting"}</div>
          </div>
        </div>

        <div className="mt-4 grid gap-2">
          <ModeButton
            active={mode === "existing"}
            label="Existing AWS"
            sublabel="AWS spend, findings, proposals, scans"
            icon={Radar}
            onClick={() => setMode("existing")}
          />
          <ModeButton
            active={mode === "new"}
            label="New AWS workload"
            sublabel="AWS architecture, budget, compliance"
            icon={BrainCircuit}
            onClick={() => setMode("new")}
          />
        </div>

        <div className="mt-4 rounded-md border border-hairline bg-surface-raised p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="eyebrow">Reasoning trace</span>
            <span className="num text-[11px] text-foreground">{toolCount}</span>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            {["Cost", "Risk", "Action"].map((label) => (
              <span key={label} className="rounded-md bg-surface px-2 py-1 text-center text-[10.5px] text-ink-dim">
                {label}
              </span>
            ))}
          </div>
        </div>

        {mode === "new" && (
          <div className="mt-4 space-y-2 rounded-md border border-hairline bg-surface-raised p-3">
            <div className="eyebrow">Workload profile</div>
            <Tabs value={form.company_size} onValueChange={(value) => updateForm("company_size", value as WorkloadForm["company_size"])}>
              <TabsList className="grid h-auto w-full grid-cols-2 rounded-md">
                <TabsTrigger value="startup" className="text-[11px]">Startup</TabsTrigger>
                <TabsTrigger value="smb" className="text-[11px]">SMB</TabsTrigger>
                <TabsTrigger value="mid_market" className="text-[11px]">Mid</TabsTrigger>
                <TabsTrigger value="enterprise" className="text-[11px]">Enterprise</TabsTrigger>
              </TabsList>
            </Tabs>
            <Input
              type="number"
              value={form.monthly_budget}
              onChange={(event) => updateForm("monthly_budget", Number(event.target.value) || 1)}
              className="h-9 text-[12px]"
            />
            <Input
              value={form.workload_type}
              onChange={(event) => updateForm("workload_type", event.target.value)}
              className="h-9 text-[12px]"
            />
            <Input
              value={form.current_storage_platform}
              onChange={(event) => updateForm("current_storage_platform", event.target.value)}
              className="h-9 text-[12px]"
            />
            <Tabs value={form.growth_expectation} onValueChange={(value) => updateForm("growth_expectation", value as WorkloadForm["growth_expectation"])}>
              <TabsList className="grid h-auto w-full grid-cols-3 rounded-md">
                <TabsTrigger value="flat" className="text-[11px]">Flat</TabsTrigger>
                <TabsTrigger value="moderate" className="text-[11px]">Moderate</TabsTrigger>
                <TabsTrigger value="high" className="text-[11px]">High</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        )}
      </aside>

      <div className="flex min-h-[680px] min-w-0 flex-col">
        <header className="border-b border-hairline px-4 py-3 sm:px-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <MessageSquareText className="size-4 text-signal" />
              <span className="text-[13px] font-semibold text-foreground">
                {mode === "existing" ? "AWS operations dialogue" : "AWS workload design dialogue"}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="rounded-md border border-border/70 px-2 py-1 text-[10.5px] text-ink-dim">No direct execution</span>
              <span className="rounded-md border border-border/70 px-2 py-1 text-[10.5px] text-ink-dim">Tenant scoped</span>
              <span className="rounded-md border border-border/70 px-2 py-1 text-[10.5px] text-ink-dim">Tool grounded</span>
            </div>
          </div>
        </header>

        <div ref={listRef} className="flex-1 space-y-4 overflow-y-auto bg-background/40 p-4 sm:p-5">
          {sessionError && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-[12px] text-destructive">
              {sessionError}
            </div>
          )}
          {messages.length === 0 && <WelcomeMessage />}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} onDecided={() => {}} />
          ))}
          {sending && (
            <div className="flex items-center gap-2 text-[12px] text-ink-faint">
              <Loader2 className="size-4 animate-spin" />
              CloudCareAI is calling the right AWS tools
            </div>
          )}
        </div>

        <div className="border-t border-hairline bg-surface p-3 sm:p-4">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {promptPack.map((prompt) => {
              const Icon = prompt.icon;
              return (
                <button
                  key={prompt.text}
                  type="button"
                  onClick={() => send(prompt.text)}
                  disabled={!sessionId || sending}
                  className="group rounded-md border border-border/70 bg-surface-raised p-2.5 text-left transition-colors hover:border-signal disabled:opacity-50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-[11.5px] font-medium text-foreground">
                      <Icon className="size-3.5 text-signal" />
                      {prompt.title}
                    </span>
                    <ArrowRight className="size-3.5 text-ink-faint transition-transform group-hover:translate-x-0.5" />
                  </div>
                  <p className="mt-1 line-clamp-2 text-[10.5px] leading-snug text-ink-faint">{prompt.text}</p>
                </button>
              );
            })}
          </div>

          <form
            className="mt-3 flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              send(input);
            }}
          >
            <Textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (canSend) send(input);
                }
              }}
              placeholder={sessionId ? "Ask CloudCareAI about AWS..." : "Starting session..."}
              disabled={!sessionId || sending}
              className="max-h-36 min-h-12 resize-none rounded-md bg-background text-[13px]"
            />
            <Button type="submit" size="sm" disabled={!canSend} className="h-12 w-12 shrink-0 rounded-md p-0">
              <Send className="size-4" />
            </Button>
          </form>
        </div>
      </div>
    </section>
  );
}
