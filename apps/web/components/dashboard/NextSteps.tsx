import { nextSteps } from "@/lib/mockData";

export default function NextSteps() {
  return (
    <div className="bg-[#EAF3EE] border border-[#CFE6DA] rounded-xl p-6">
      <h3 className="font-display text-[15px] font-semibold text-[#173404] mb-1">What&apos;s next</h3>
      <p className="text-[13px] text-[#3B6D11] mb-4">
        A few steps to take CloudCare from prototype to production-ready.
      </p>
      <ol className="flex flex-col gap-2.5">
        {nextSteps.map((step, i) => (
          <li key={step} className="flex items-start gap-3 text-[13.5px] text-[#173404]">
            <span className="flex-none w-5 h-5 rounded-full bg-[#3FA796] text-white text-[11px] font-semibold flex items-center justify-center mt-0.5">
              {i + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
    </div>
  );
}
