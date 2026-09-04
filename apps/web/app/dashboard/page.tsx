"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ShieldCheck, ArrowRight } from "lucide-react";
import { getDemoSession, type DemoSession } from "@/lib/auth";
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

// NOTE: this route is protected client-side only, which is fine for a demo.
// PLACEHOLDER: once real auth exists, protect this route server-side with
// Next.js middleware (middleware.ts) checking a session cookie instead.
export default function DashboardPage() {
  const router = useRouter();
  const [session, setSession] = useState<DemoSession | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const s = getDemoSession();
    if (!s) {
      router.replace("/login");
      return;
    }
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
    fetch(`${apiBaseUrl}/v1/auth/me`, { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("Backend session invalid");
        return res.json();
      })
      .then((data) => {
        setSession({
          userId: data.user_id || s.userId,
          loggedInAt: s.loggedInAt,
        });
        setChecked(true);
      })
      .catch((err) => {
        console.warn("Session validation failed, using active local session:", err);
        setSession(s);
        setChecked(true);
      });
  }, [router]);

  if (!checked || !session) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-bg">
        <p className="text-inkFaint text-sm">Loading dashboard…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-bg flex">
      <Sidebar />
      <div className="flex-1 min-w-0">
        <DashboardHeader userId={session.userId} />
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

          <Link
            href="/finops"
            className="group flex items-center justify-between bg-surface border border-line rounded-xl p-5 shadow-card hover:border-brandTeal transition-colors"
          >
            <div className="flex items-center gap-3">
              <span className="w-9 h-9 rounded-full bg-surfaceAlt2 flex items-center justify-center">
                <ShieldCheck size={16} className="text-brandTeal" />
              </span>
              <div>
                <p className="text-[14px] font-semibold text-ink">FinOps Intelligence</p>
                <p className="text-[12.5px] text-inkFaint">
                  Spend velocity guard, cost attribution, and unit economics — SpendShield · DollarTrace · MarginOS
                </p>
              </div>
            </div>
            <ArrowRight size={16} className="text-inkFaint group-hover:text-brandTeal group-hover:translate-x-0.5 transition-all" />
          </Link>

          <NextSteps />
        </div>
      </div>
    </main>
  );
}
