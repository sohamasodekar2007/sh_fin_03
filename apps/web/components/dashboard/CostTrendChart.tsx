"use client";

import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { fetchCostTrend } from "@/lib/api";
import { costTrend as mockCostTrend } from "@/lib/mockData";

export default function CostTrendChart() {
  const [trend, setTrend] = useState(mockCostTrend);

  useEffect(() => {
    fetchCostTrend().then(setTrend);
  }, []);

  return (
    <div className="bg-surface border border-line rounded-xl p-5">
      <p className="text-[13px] font-semibold text-ink mb-1">Cost trend — last 30 days</p>
      <p className="text-[12px] text-inkFaint mb-4">Daily spend, USD.</p>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={trend} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#DCE7EC" />
            <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#8CA0AE" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: "#8CA0AE" }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ borderRadius: 10, borderColor: "#DCE7EC", fontSize: 12 }} formatter={(value: number) => [`$${value}`, "Cost"]} />
            <Line type="monotone" dataKey="cost" stroke="#2F6690" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}