"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  BookOpenCheck,
  Cloud,
  Boxes,
  Database,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  MessageCircle,
  PlugZap,
  Server,
  ShieldAlert,
  ShieldCheck,
  Zap,
} from "lucide-react";

/**
 * Left nav for the dashboard shell (apps/frontend/src/app/dashboard/layout.tsx).
 * Plain <Link> + usePathname() active-state — no client state to lift,
 * each item is a real Next.js route so back/forward and deep-linking work.
 */

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/dashboard/resources", label: "Resources", icon: Server, exact: false },
  { href: "/dashboard/aws-core-services", label: "AWS Core Services", icon: Boxes, exact: false },
  { href: "/dashboard/parquet-analysis", label: "Parquet Analysis", icon: Database, exact: false },
  { href: "/dashboard/proposals", label: "Proposals", icon: ListChecks, exact: false },
  { href: "/dashboard/agent-command", label: "Agent Command", icon: GitBranch, exact: false },
  { href: "/dashboard/agent-activity", label: "Agent Activity", icon: Bot, exact: false },
  { href: "/dashboard/setup-guide", label: "Setup Guide", icon: BookOpenCheck, exact: false },
  { href: "/dashboard/connected-providers", label: "Connected Providers", icon: Cloud, exact: false },
  { href: "/dashboard/governance", label: "IAM & Governance", icon: ShieldCheck, exact: false },
  { href: "/dashboard/security-findings", label: "Security Findings", icon: ShieldAlert, exact: false },
  { href: "/dashboard/cloudcareai", label: "CloudCareAI", icon: MessageCircle, exact: false },
  { href: "/dashboard/chatbot-mcp", label: "Chatbot MCP", icon: PlugZap, exact: false },
  { href: "/dashboard/finops", label: "FinOps Intelligence", icon: Zap, exact: false },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav aria-label="Dashboard sections" className="flex flex-col gap-0.5 p-2">
      {NAV_ITEMS.map((item) => {
        const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className="flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
            style={{
              color: active ? "var(--foreground)" : "var(--ink-dim)",
              background: active ? "var(--accent)" : "transparent",
            }}
          >
            <Icon className="size-4 shrink-0" style={{ color: active ? "var(--signal)" : "var(--ink-faint)" }} />
            <span className="truncate">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
