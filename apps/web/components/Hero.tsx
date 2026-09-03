export default function Hero() {
  return (
    <section id="home" className="relative overflow-hidden pt-42 pb-24 pt-[168px]">
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute w-[380px] h-[380px] rounded-full blur-[60px] opacity-55 -top-[120px] -right-[60px] bg-[radial-gradient(circle,#BFE0F0,transparent_70%)] animate-float" />
        <div className="absolute w-[280px] h-[280px] rounded-full blur-[60px] opacity-55 top-[220px] -left-[100px] bg-[radial-gradient(circle,#BEE9DD,transparent_70%)] animate-float [animation-delay:-4s]" />
        <div className="absolute w-[220px] h-[220px] rounded-full blur-[60px] opacity-55 -bottom-[60px] right-[220px] bg-[radial-gradient(circle,#F3DFB6,transparent_70%)] animate-float [animation-delay:-8s]" />
      </div>

      <div className="relative z-10 mx-auto max-w-3xl px-7 text-center">
        <div className="inline-flex items-center gap-2 font-mono text-[12.5px] tracking-wide text-brandBlueDeep bg-surfaceAlt border border-[#CFE3EC] px-4 py-1.5 rounded-full mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-brandTeal animate-pulse-dot" />
          AI agents, watching your cloud, right now
        </div>

        <h1 className="font-display font-bold leading-[1.06] tracking-tight text-[clamp(38px,5.4vw,64px)] text-ink">
          Your cloud spend,
          <br />
          <span className="text-brandBlue">understood before it hurts.</span>
        </h1>

        <p className="mt-6 mx-auto max-w-xl text-lg text-inkSoft">
          CloudCare continuously watches your AWS infrastructure, finds the waste hiding in idle and
          over-provisioned resources, and fixes it automatically — never touching production without a
          human&apos;s yes.
        </p>

        <div className="flex gap-4 justify-center mt-9 flex-wrap">
          <a
            href="/login"
            className="inline-flex items-center justify-center gap-2 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white hover:-translate-y-0.5 hover:shadow-[0_10px_20px_-8px_rgba(16,34,46,0.4)] transition-all"
          >
            See it in action
          </a>
          <a
            href="#pipeline"
            className="inline-flex items-center justify-center gap-2 rounded-full border-[1.5px] border-line px-6 py-3 text-sm font-semibold text-ink hover:border-brandBlue hover:text-brandBlue hover:-translate-y-0.5 transition-all"
          >
            How it works ↓
          </a>
        </div>

        <div className="flex justify-center gap-12 mt-16 flex-wrap">
          {[
            { num: "30%", label: "AVG. CLOUD WASTE" },
            { num: "5", label: "SPECIALIZED AGENTS" },
            { num: "0", label: "UNAUTHORIZED ACTIONS" },
          ].map((s) => (
            <div key={s.label} className="text-center">
              <div className="font-display text-3xl font-bold text-ink">{s.num}</div>
              <div className="text-[12.5px] font-mono text-inkFaint mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
