"use client";

import { useEffect, useState } from "react";
import { pipelineStages } from "@/lib/mockData";

export default function Pipeline() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;
    const id = setInterval(() => setActive((i) => (i + 1) % pipelineStages.length), 900);
    return () => clearInterval(id);
  }, []);

  return (
    <section id="pipeline" className="pt-16 pb-24">
      <div className="mx-auto max-w-6xl px-7">
        <div className="text-center mb-13">
          <div className="font-mono text-[12.5px] text-brandTeal tracking-wide uppercase">
            The safe agentic workflow
          </div>
          <h2 className="font-display font-bold text-[clamp(26px,3.4vw,36px)] mt-2.5 text-ink">
            Seven stages. Every action explained.
          </h2>
        </div>

        <div className="relative flex flex-wrap justify-between items-start max-w-4xl mx-auto gap-y-7 gap-x-2">
          {pipelineStages.map((stage, i) => {
            const isLit = i <= active;
            return (
              <div key={stage.title} className="relative z-10 flex-1 min-w-[100px] flex flex-col items-center text-center px-1.5">
                <div
                  className={`w-13 h-13 w-[52px] h-[52px] rounded-full flex items-center justify-center border-2 font-display font-bold text-[13px] mb-3.5 transition-all duration-500 ${
                    isLit
                      ? "border-brandTeal text-brandTeal bg-[#EAFAF5] shadow-[0_0_0_6px_rgba(63,167,150,0.12)]"
                      : "border-line text-inkFaint bg-surface"
                  }`}
                >
                  {String(i + 1).padStart(2, "0")}
                </div>
                <div className="text-[13.5px] font-bold text-ink mb-1">{stage.title}</div>
                <div className="text-[11.5px] text-inkFaint max-w-[110px] leading-tight">{stage.desc}</div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
