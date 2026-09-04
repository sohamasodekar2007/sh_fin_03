"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck } from "lucide-react";

const items = [
  { key: "overview", label: "Overview", icon: "▦" },
  { key: "resources", label: "Resources", icon: "▤" },
  { key: "activity", label: "Agent activity", icon: "◷" },
  { key: "before-after", label: "Before / after", icon: "⇄" },
  { key: "sim", label: "Sim control", icon: "▶" },
  { key: "settings", label: "Settings", icon: "⚙" },
];

export default function Sidebar() {
  const [active, setActive] = useState("overview");
  const pathname = usePathname();
  const onFinops = pathname?.startsWith("/finops");

  return (
    <aside className="hidden md:flex w-56 flex-none flex-col border-r border-line bg-surface min-h-screen py-6 px-3">
      <nav className="flex flex-col gap-1">
        {items.map((item) => (
          <button
            key={item.key}
            onClick={() => setActive(item.key)}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-[14px] font-medium text-left transition-colors ${
              !onFinops && active === item.key
                ? "bg-surfaceAlt text-brandBlueDeep"
                : "text-inkSoft hover:bg-surfaceAlt hover:text-ink"
            }`}
          >
            <span className="w-5 text-center text-inkFaint">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      {/* Real route (not a placeholder tab) — SpendShield-lite / DollarTrace-lite / MarginOS-lite */}
      <div className="mt-4 pt-4 border-t border-line">
        <Link
          href="/finops"
          className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-[14px] font-medium transition-colors ${
            onFinops
              ? "bg-surfaceAlt2 text-brandBlueDeep"
              : "text-inkSoft hover:bg-surfaceAlt2 hover:text-ink"
          }`}
        >
          <ShieldCheck size={16} className={onFinops ? "text-brandTeal" : "text-inkFaint"} />
          FinOps Intelligence
        </Link>
      </div>

      {!onFinops && active !== "overview" && (
        <p className="mt-4 mx-3.5 text-[12.5px] text-inkFaint">
          This view is a placeholder in the prototype — wire it up to real data once the backend is connected.
        </p>
      )}
    </aside>
  );
}
