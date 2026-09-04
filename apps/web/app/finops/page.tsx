"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getDemoSession, type DemoSession } from "@/lib/auth";
import Sidebar from "@/components/dashboard/Sidebar";
import DashboardHeader from "@/components/dashboard/DashboardHeader";
import SpendVelocityCard from "@/components/dashboard/SpendVelocityCard";
import CostBreakdownPanel from "@/components/dashboard/CostBreakdownPanel";
import UnitEconomicsCard from "@/components/dashboard/UnitEconomicsCard";

// Dedicated route for the fintech add-ons (SpendShield-lite / DollarTrace-lite /
// MarginOS-lite) — backed by cloudcare-fintech-addons/api, a standalone FastAPI
// service on NEXT_PUBLIC_ADDON_API_URL, not the main backend. To remove: delete
// this route + the three files in components/dashboard/ + cloudcare-fintech-addons/
// + the "FinOps Intelligence" nav link in Sidebar.tsx. Nothing else references them.
//
// Same client-side session guard as /dashboard (see the PLACEHOLDER note there
// about moving this to server-side middleware once real auth exists), kept
// intentionally lighter — no re-validation call against the main backend — since
// this route's own data comes entirely from the add-on API, not the main one.
export default function FinOpsPage() {
  const router = useRouter();
  const [session, setSession] = useState<DemoSession | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const s = getDemoSession();
    if (!s) {
      router.replace("/login?returnTo=/finops");
      return;
    }
    setSession(s);
    setChecked(true);
  }, [router]);

  if (!checked || !session) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-bg">
        <p className="text-inkFaint text-sm">Loading FinOps intelligence…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-bg flex">
      <Sidebar />
      <div className="flex-1 min-w-0">
        <DashboardHeader userId={session.userId} />
        <div className="p-7 flex flex-col gap-6 max-w-6xl">
          <div>
            <p className="text-[12.5px] text-inkFaint uppercase tracking-wide mb-1">FinOps Intelligence</p>
            <h1 className="font-display text-2xl font-semibold text-ink mb-2">
              SpendShield · DollarTrace · MarginOS
            </h1>
            <p className="text-[13.5px] text-inkSoft max-w-3xl leading-relaxed">
              Three category-defining features layered on top of the core 5-agent pipeline: a real-time spend-velocity
              circuit breaker, cost-delta attribution ranked by contribution, and gross-margin economics per merchant.
              Live data below is served by a standalone add-on API (
              <code className="font-mono text-[12px] bg-surfaceAlt px-1.5 py-0.5 rounded">cloudcare-fintech-addons/api</code>
              ), separate from the main backend — see that folder's README for the merge path.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <SpendVelocityCard />
            <CostBreakdownPanel />
          </div>

          <UnitEconomicsCard />
        </div>
      </div>
    </main>
  );
}
