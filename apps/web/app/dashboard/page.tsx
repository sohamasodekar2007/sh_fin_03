"use client";

import { useSession } from "next-auth/react";
import MonitorAgentControl from "@/components/dashboard/MonitorAgentControl";
import AnalyzerAgentControl from "@/components/dashboard/AnalyzerAgentControl";
import Sidebar from "@/components/dashboard/Sidebar";
import DashboardHeader from "@/components/dashboard/DashboardHeader";
import KpiCards from "@/components/dashboard/KpiCards";
import CostTrendChart from "@/components/dashboard/CostTrendChart";
import HealthDonut from "@/components/dashboard/HealthDonut";
import AgentFeed from "@/components/dashboard/AgentFeed";
import ResourceTable from "@/components/dashboard/ResourceTable";
import NextSteps from "@/components/dashboard/NextSteps";

// middleware.ts already protects this route server-side (redirects to
// /login when there's no NextAuth session) — this client-side status check
// is only for the loading state, not for auth gating.
export default function DashboardPage() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <main className="min-h-screen flex items-center justify-center bg-bg">
        <p className="text-inkFaint text-sm">Loading dashboard…</p>
      </main>
    );
  }

  const userId = session?.user?.name || session?.user?.email || "Demo User";

  return (
    <main className="min-h-screen bg-bg flex">
      <Sidebar />
      <div className="flex-1 min-w-0">
        <DashboardHeader userId={userId} />
        <div className="p-7 flex flex-col gap-6 max-w-6xl">
          <MonitorAgentControl />
          <AnalyzerAgentControl />
          <KpiCards />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CostTrendChart />
            <HealthDonut />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <AgentFeed />
            <ResourceTable />
          </div>
          <NextSteps />
        </div>
      </div>
    </main>
  );
}
