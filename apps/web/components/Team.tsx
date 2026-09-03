import { teamMembers } from "@/lib/mockData";
import Reveal from "./Reveal";

export default function Team() {
  return (
    <section id="team" className="py-24 bg-surfaceAlt">
      <div className="mx-auto max-w-6xl px-7">
        <Reveal className="max-w-xl mx-auto mb-13 text-center">
          <div className="font-mono text-[12.5px] text-brandBlue tracking-wide uppercase">Team Alpha</div>
          <h2 className="font-display font-bold text-[clamp(26px,3.4vw,38px)] mt-2.5 text-ink">
            The people behind CloudCare
          </h2>
          <p className="mt-3.5 text-base text-inkSoft">
            Pimpri Chinchwad College of Engineering, Pune — built for Smart Horizon 2026.
          </p>
        </Reveal>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-5">
          {teamMembers.map((m) => (
            <div
              key={m.name}
              className="bg-surface border border-line rounded-lg2 p-6.5 px-4.5 text-center hover:-translate-y-1.5 hover:-rotate-1 hover:shadow-soft transition-all duration-300"
            >
              <div
                className="w-[66px] h-[66px] rounded-full mx-auto mb-4 flex items-center justify-center font-display font-bold text-[19px] text-white"
                style={{ background: `linear-gradient(135deg, ${m.from}, ${m.to})` }}
              >
                {m.initials}
              </div>
              <h4 className="text-[14.5px] font-semibold mb-1 leading-tight text-ink">{m.name}</h4>
              <div className="font-mono text-[11px] text-inkFaint">{m.role}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
