"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

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

  return (
    <aside className="hidden md:flex w-56 flex-none flex-col border-r border-line bg-surface min-h-screen py-6 px-3">
      <nav className="flex flex-col gap-1">
        <Link
          href="/chat"
          className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-[14px] font-medium text-left transition-colors ${
            pathname === "/chat" ? "bg-surfaceAlt text-brandBlueDeep" : "text-inkSoft hover:bg-surfaceAlt hover:text-ink"
          }`}
        >
          <span className="w-5 text-center text-inkFaint">💬</span>
          Chat
        </Link>
        {items.map((item) => (
          <button
            key={item.key}
            onClick={() => setActive(item.key)}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-[14px] font-medium text-left transition-colors ${
              active === item.key && pathname !== "/chat"
                ? "bg-surfaceAlt text-brandBlueDeep"
                : "text-inkSoft hover:bg-surfaceAlt hover:text-ink"
            }`}
          >
            <span className="w-5 text-center text-inkFaint">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      {active !== "overview" && pathname !== "/chat" && (
        <p className="mt-4 mx-3.5 text-[12.5px] text-inkFaint">
          This view is a placeholder in the prototype — wire it up to real data once the backend is connected.
        </p>
      )}
    </aside>
  );
}
