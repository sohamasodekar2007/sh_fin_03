"use client";

import { useState, useRef, useEffect } from "react";
import { getAuthHeaders } from "@/lib/auth";
import ApprovalCard, { type ApprovalCardPayload } from "@/components/chat/ApprovalCard";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  ui?: ApprovalCardPayload | null;
}

const SUGGESTIONS = ["Scan my cloud", "Show wasted resources", "What's my spend?", "What needs my approval?"];

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Hi — I'm the CloudCare assistant. I can run a scan, list wasted resources, summarize spend, or show what's pending your approval.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMessage: Message = { id: crypto.randomUUID(), role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${BASE_URL}/v1/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify({
          messages: [...messages, userMessage].map((m) => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { id: data.id || crypto.randomUUID(), role: "assistant", content: data.content, ui: data.ui },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: "Couldn't reach the backend — is the FastAPI server running?" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)] max-w-2xl mx-auto bg-surface border border-line rounded-lg2 shadow-soft m-4 overflow-hidden">
      <div className="px-6 py-4 border-b border-line">
        <h1 className="font-display font-bold text-lg text-ink">CloudCare Assistant</h1>
        <p className="text-xs text-inkFaint">Backed by the same 5-agent pipeline as the dashboard — not a separate chatbot.</p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-4">
        {messages.map((m) => (
          <div key={m.id} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
            <div
              className={`max-w-sm rounded-2xl px-4 py-2.5 text-[13.5px] leading-snug ${
                m.role === "user" ? "bg-ink text-white" : "bg-bg text-ink border border-line"
              }`}
            >
              {m.content}
            </div>
            {m.ui && <ApprovalCard payload={m.ui} />}
          </div>
        ))}
        {loading && <div className="text-xs text-inkFaint">CloudCare is thinking…</div>}
      </div>

      <div className="px-6 py-2 flex gap-2 flex-wrap">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => send(s)}
            className="text-[11.5px] px-3 py-1.5 rounded-full border border-line text-inkSoft hover:border-brandBlue hover:text-brandBlue transition-all"
          >
            {s}
          </button>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="p-4 border-t border-line flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your cloud spend…"
          disabled={loading}
          className="flex-1 border-[1.5px] border-line rounded-full px-4 py-2.5 text-[13.5px] bg-bg focus:outline-none focus:border-brandBlue transition-all disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
