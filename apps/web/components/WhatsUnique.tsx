import Reveal from "./Reveal";

const items = [
  {
    tag: "// SURGICAL LLM",
    title: "AI only where it earns its place",
    desc: "Monitor and Analyzer run on deterministic rules. Only Decision and Supervisor use LLM reasoning — the Executor never touches a language model at all.",
  },
  {
    tag: "// TRACEABLE",
    title: "Five agents, one shared state",
    desc: "Agents never call each other directly — every observation, proposal and approval passes through one auditable shared state.",
  },
  {
    tag: "// SAFETY-FIRST",
    title: "Production is a locked door",
    desc: "env=prod resources can never auto-execute. High-risk actions always wait for a human, with a policy engine that can't be argued with.",
  },
  {
    tag: "// EXPLAINABLE",
    title: "Verified, not estimated, savings",
    desc: "Every action closes only after a post-change health and savings check — so the number you see is the number that actually happened.",
  },
];

export default function WhatsUnique() {
  return (
    <section className="py-24">
      <div className="mx-auto max-w-6xl px-7">
        <Reveal className="max-w-xl mx-auto mb-13 text-center">
          <div className="font-mono text-[12.5px] text-brandBlue tracking-wide uppercase">What&apos;s unique in us</div>
          <h2 className="font-display font-bold text-[clamp(26px,3.4vw,38px)] mt-2.5 text-ink">
            AI where judgment matters. Rules where safety matters.
          </h2>
          <p className="mt-3.5 text-base text-inkSoft">
            CloudCare never lets a language model touch your infrastructure directly — it can only recommend
            within a system built to say no.
          </p>
        </Reveal>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {items.map((it) => (
            <div
              key={it.title}
              className="bg-surface border border-line rounded-lg2 p-7.5 p-[30px] hover:-translate-y-1.5 hover:shadow-soft transition-all duration-300"
            >
              <div className="font-mono text-[12.5px] text-inkFaint mb-3.5">{it.tag}</div>
              <h4 className="text-lg font-display font-semibold mb-2.5 text-ink">{it.title}</h4>
              <p className="text-[14.5px] text-inkSoft">{it.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
