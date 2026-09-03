"use client";

import { useRef } from "react";
import { featureCards } from "@/lib/mockData";
import Reveal from "./Reveal";

export default function FeatureSlider() {
  const trackRef = useRef<HTMLDivElement>(null);

  const scroll = (dir: number) => {
    trackRef.current?.scrollBy({ left: dir * 320, behavior: "smooth" });
  };

  return (
    <section className="py-24">
      <div className="mx-auto max-w-6xl px-7">
        <Reveal className="flex justify-between items-end mb-8 flex-wrap gap-5">
          <div>
            <div className="font-mono text-[12.5px] text-brandBlue tracking-wide uppercase">Under the hood</div>
            <h2 className="font-display font-bold text-[clamp(22px,3vw,32px)] mt-2.5 text-ink max-w-lg">
              Built to find money, not just spend it wisely on dashboards.
            </h2>
          </div>
          <div className="flex gap-2.5">
            <button
              onClick={() => scroll(-1)}
              aria-label="Previous"
              className="w-10.5 h-10.5 w-[42px] h-[42px] rounded-full border-[1.5px] border-line bg-surface flex items-center justify-center hover:border-brandBlue hover:bg-surfaceAlt transition-all"
            >
              ←
            </button>
            <button
              onClick={() => scroll(1)}
              aria-label="Next"
              className="w-10.5 h-10.5 w-[42px] h-[42px] rounded-full border-[1.5px] border-line bg-surface flex items-center justify-center hover:border-brandBlue hover:bg-surfaceAlt transition-all"
            >
              →
            </button>
          </div>
        </Reveal>

        <div ref={trackRef} className="flex gap-5 overflow-x-auto pb-4.5 snap-x snap-mandatory scrollbar-thin">
          {featureCards.map((f) => (
            <div
              key={f.title}
              className="snap-start flex-none w-[300px] bg-surface border border-line rounded-lg2 p-7 hover:-translate-y-1.5 hover:shadow-soft hover:border-[#C9DEE8] transition-all duration-300"
            >
              <div className="font-mono text-[11px] text-brandTeal bg-[#EAFAF5] inline-block px-2.5 py-1 rounded-full mb-4">
                {f.tag}
              </div>
              <h4 className="text-[17px] font-display font-semibold mb-2.5 leading-snug text-ink">{f.title}</h4>
              <p className="text-sm text-inkSoft">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
