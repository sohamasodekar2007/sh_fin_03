"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";

import { Sidebar } from "@/components/cfo/Sidebar";
import { Button } from "@/components/ui/button";
import { setToken } from "@/lib/api";

/**
 * Shared shell for every /dashboard/* route — masthead + left sidebar nav.
 * ControlBar (provider/period filters) stays local to the Overview page,
 * not lifted here: Resources has its own environment/status filters and
 * the other pages don't share Overview's filter shape, so there's nothing
 * to gain from forcing a single global filter state.
 */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();

  function handleSignOut() {
    setToken(null);
    router.push("/login");
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-hairline bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1680px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: "var(--mint)" }} />
            <span className="eyebrow hover:text-ink-dim">CloudCare · Dashboard</span>
          </Link>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href="/onboarding">Connect another provider</Link>
            </Button>
            <Button variant="ghost" size="sm" onClick={handleSignOut}>
              <LogOut className="size-4" /> Sign out
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-[1680px] items-start gap-0 px-0 sm:px-0">
        <aside className="sticky top-[57px] hidden h-[calc(100vh-57px)] w-56 shrink-0 overflow-y-auto border-r border-hairline lg:block">
          <Sidebar />
        </aside>
        <main className="min-w-0 flex-1 px-4 pb-20 pt-4 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
