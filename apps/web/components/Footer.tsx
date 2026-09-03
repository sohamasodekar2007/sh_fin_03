export default function Footer() {
  return (
    <footer className="bg-ink text-[#B9C7D1] pt-14 pb-7 mt-10">
      <div className="mx-auto max-w-6xl px-7">
        <div className="flex justify-between items-start flex-wrap gap-8 pb-9 border-b border-white/10">
          <div className="flex items-center gap-2.5 font-display font-bold text-lg text-white">
            <span className="w-8 h-8 rounded-[10px] bg-gradient-to-br from-brandBlue to-brandTeal inline-block" />
            CloudCare
          </div>
          <div className="flex gap-11 flex-wrap">
            <div>
              <h5 className="font-mono text-[12.5px] text-[#8CA0AE] uppercase tracking-wide mb-3.5">Navigate</h5>
              {[
                ["Home", "/#home"],
                ["About", "/#about"],
                ["Team", "/#team"],
                ["Contact us", "/#contact"],
              ].map(([label, href]) => (
                <a key={label} href={href} className="block text-sm text-[#D6E0E6] mb-2.5 hover:text-brandTeal transition-colors">
                  {label}
                </a>
              ))}
            </div>
            <div>
              <h5 className="font-mono text-[12.5px] text-[#8CA0AE] uppercase tracking-wide mb-3.5">Project</h5>
              <p className="text-sm text-[#D6E0E6] mb-2.5">Problem ID: SH-FIN-03</p>
              <p className="text-sm text-[#D6E0E6] mb-2.5">Smart Horizon 2026</p>
              <p className="text-sm text-[#D6E0E6] mb-2.5">Team Alpha, PCCOE Pune</p>
            </div>
          </div>
        </div>
        <div className="flex justify-between pt-5.5 pt-[22px] text-[13px] flex-wrap gap-2.5">
          <span className="text-[#8CA0AE]">© 2026 CloudCare — built for Smart Horizon 2026.</span>
          <span className="text-[#8CA0AE]">AI-Powered Cloud Cost Optimization & Resource Intelligence Platform</span>
        </div>
      </div>
    </footer>
  );
}
