"use client";

import { useEffect, useRef, useState } from "react";
import Reveal from "./Reveal";

const points = [
  { title: "Nobody notices the waste", desc: "A test server spun up in March is often still running — and still billed — in October." },
  { title: "Nobody predicts the bill", desc: "Costs creep quietly until finance gets a number nobody saw coming." },
  { title: "Fixing it is manual and rare", desc: "Cleanup means someone digging through dashboards by hand — so it barely happens." },
];

export default function WhyCloudCare() {
  const barRef = useRef<HTMLDivElement>(null);
  const [filled, setFilled] = useState(false);

  useEffect(() => {
    const el = barRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setFilled(true);
          io.disconnect();
        }
      },
      { threshold: 0.4 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section className="py-24 bg-surfaceAlt">
      <div className="mx-auto max-w-6xl px-7 grid grid-cols-1 md:grid-cols-2 gap-14 items-center">
        <Reveal>
          <div className="font-mono text-[12.5px] text-brandTeal tracking-wide uppercase">Why CloudCare</div>
          <h2 className="font-display font-bold text-[clamp(24px,3vw,34px)] mt-2.5 text-ink">
            Cloud bills don&apos;t explain themselves. We built something that does.
          </h2>
          <div className="mt-7 flex flex-col gap-4.5">
            {points.map((p, i) => (
              <div key={p.title} className="flex gap-4 items-start">
                <div className="flex-none w-8.5 h-8.5 w-[34px] h-[34px] rounded-[9px] bg-surfaceAlt2 flex items-center justify-center text-brandTeal font-bold text-sm">
                  {i + 1}
                </div>
                <div>
                  <h4 className="text-[15.5px] font-semibold mb-1 text-ink">{p.title}</h4>
                  <p className="text-sm text-inkSoft">{p.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </Reveal>

        <Reveal>
          <div className="bg-ink rounded-lg2 p-9 text-white relative overflow-hidden">
            <div className="absolute w-[220px] h-[220px] rounded-full -top-20 -right-16 bg-[radial-gradient(circle,rgba(63,167,150,0.35),transparent_70%)]" />
            <div className="font-display text-6xl font-bold relative">
              30<span className="text-brandTeal">–35%</span>
            </div>
            <p className="text-[#B9C7D1] relative mt-3 text-[15px]">
              of global cloud spend is estimated to be wasted on idle and over-provisioned infrastructure.
            </p>
            <div ref={barRef} className="mt-6.5 h-2.5 rounded-full bg-white/10 overflow-hidden relative">
              <div
                className="h-full rounded-full bg-gradient-to-r from-brandTeal to-[#7fd6c4] transition-all duration-[1400ms] ease-out"
                style={{ width: filled ? "32%" : "0%" }}
              />
            </div>
            <p className="mt-2.5 text-[12.5px] text-[#B9C7D1]">
              CloudCare&apos;s initial target: identify at least 10% of analyzed EC2 spend as recoverable.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
