"use client";

import Reveal from "./Reveal";

export default function Contact() {
  return (
    <section id="contact" className="py-24">
      <div className="mx-auto max-w-6xl px-7 grid grid-cols-1 md:grid-cols-[0.9fr_1.1fr] gap-14 items-start">
        <Reveal>
          <div className="font-mono text-[12.5px] text-brandBlue tracking-wide uppercase">Get in touch</div>
          <h2 className="font-display font-bold text-[clamp(24px,3vw,32px)] mt-2.5 text-ink">
            Questions for the team?
          </h2>
          <p className="mt-4 text-[15.5px] max-w-sm text-inkSoft">
            Whether you&apos;re a judge, a mentor, or just curious how the agents talk to each other — we&apos;re
            happy to walk you through it.
          </p>
          <div className="mt-7 flex flex-col gap-3.5">
            {[
              ["✉", "hello.cloudcare@teamalpha.dev"],
              ["📍", "PCCOE, Pune, Maharashtra"],
              ["🏆", "Smart Horizon 2026 · Problem SH-FIN-03"],
            ].map(([icon, text]) => (
              <div key={text} className="flex gap-3 items-center text-[14.5px] text-inkSoft">
                <span className="w-8.5 h-8.5 w-[34px] h-[34px] rounded-[9px] bg-surfaceAlt2 flex items-center justify-center text-[15px]">
                  {icon}
                </span>
                {text}
              </div>
            ))}
          </div>
        </Reveal>

        <Reveal>
          <form
            className="bg-surface border border-line rounded-lg2 p-8.5 p-[34px] flex flex-col gap-4.5"
            onSubmit={(e) => e.preventDefault()}
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Name</label>
                <input
                  type="text"
                  placeholder="Your name"
                  className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all"
                />
              </div>
              <div>
                <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Email</label>
                <input
                  type="email"
                  placeholder="you@example.com"
                  className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all"
                />
              </div>
            </div>
            <div>
              <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Subject</label>
              <input
                type="text"
                placeholder="What's this about?"
                className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all"
              />
            </div>
            <div>
              <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Message</label>
              <textarea
                placeholder="Tell us a bit more..."
                rows={4}
                className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all resize-y"
              />
            </div>
            <button
              type="submit"
              className="self-start inline-flex items-center justify-center rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white hover:-translate-y-0.5 hover:shadow-[0_10px_20px_-8px_rgba(16,34,46,0.4)] transition-all"
            >
              Send message
            </button>
          </form>
        </Reveal>
      </div>
    </section>
  );
}
