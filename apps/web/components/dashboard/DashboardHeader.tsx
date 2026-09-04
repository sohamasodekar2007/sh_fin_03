"use client";

import { useRouter } from "next/navigation";
import { demoLogout } from "@/lib/auth";

export default function DashboardHeader({ userId }: { userId: string }) {
  const router = useRouter();

  const handleLogout = () => {
    demoLogout();
    router.push("/");
  };

  const initials = userId
    .split(/[.\s_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("") || "DU";

  return (
    <header className="flex items-center justify-between px-7 py-5 border-b border-line bg-surface">
      <div>
        <p className="text-[13px] text-inkFaint">Welcome back</p>
        <h1 className="font-display text-lg font-semibold text-ink">{userId || "Demo User"}</h1>
      </div>
      <div className="flex items-center gap-4">
        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-brandBlue to-brandTeal flex items-center justify-center text-white text-[13px] font-semibold">
          {initials}
        </div>
        <button
          onClick={handleLogout}
          className="inline-flex items-center justify-center rounded-full border-[1.5px] border-line px-4 py-2 text-[13.5px] font-semibold text-ink hover:border-brandBlue hover:text-brandBlue transition-all"
        >
          Log out
        </button>
      </div>
    </header>
  );
}
