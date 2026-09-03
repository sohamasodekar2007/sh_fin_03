import Reveal from "./Reveal";

const personas = [
  {
    icon: "⚙",
    bg: "#E4EEF3",
    color: "#2F6690",
    title: "Engineering & DevOps",
    desc: "See exactly which resources are safe to touch, with evidence, ownership, and runbooks — no guesswork before a change.",
  },
  {
    icon: "$",
    bg: "#EAFAF5",
    color: "#3FA796",
    title: "FinOps & Finance",
    desc: "Get accurate forecasts, a savings ledger, and cost allocation you can actually take to a budget meeting.",
  },
  {
    icon: "◈",
    bg: "#FBF1DE",
    color: "#B8842E",
    title: "Leadership",
    desc: "A single view of business impact, risk, and trend — without needing to read a single AWS bill line by line.",
  },
];

export default function About() {
  return (
    <section id="about" className="py-24 bg-surfaceAlt">
      <div className="mx-auto max-w-6xl px-7">
        <Reveal className="max-w-xl mx-auto mb-13 text-center">
          <div className="font-mono text-[12.5px] text-brandBlue tracking-wide uppercase">What CloudCare does</div>
          <h2 className="font-display font-bold text-[clamp(26px,3.4vw,38px)] mt-2.5 text-ink">
            One platform, three teams, one shared truth.
          </h2>
          <p className="mt-3.5 text-base text-inkSoft">
            CloudCare turns scattered AWS telemetry and billing data into decisions everyone can trust — and act on.
          </p>
        </Reveal>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {personas.map((p) => (
            <div
              key={p.title}
              className="bg-surface border border-line rounded-lg2 p-7 hover:-translate-y-1.5 hover:shadow-soft transition-all duration-300"
            >
              <div
                className="w-11 h-11 rounded-xl flex items-center justify-center text-xl mb-4.5"
                style={{ background: p.bg, color: p.color }}
              >
                {p.icon}
              </div>
              <h4 className="text-lg font-display font-semibold mb-2 text-ink">{p.title}</h4>
              <p className="text-[14.5px] text-inkSoft">{p.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
