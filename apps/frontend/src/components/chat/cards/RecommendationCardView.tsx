import { Money } from "@/components/Money";
import type { RecommendationCard } from "@/lib/cloudcare-data";

export function RecommendationCardView({ card }: { card: RecommendationCard }) {
  return (
    <div className="mt-2 rounded-md border border-border/70 bg-surface-raised/60 p-3.5">
      <div className="eyebrow">Recommendation</div>
      <p className="mt-1.5 text-[12.5px] leading-relaxed text-foreground/85">{card.summary}</p>
      <Money value={card.estimated_monthly_cost_usd} compact className="mt-2 text-base font-medium" style={{ color: "var(--mint)" }} />
      <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-faint">{card.reasoning}</p>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {card.options.map((opt, i) => (
          <div key={i} className="rounded-md border border-border/60 bg-surface p-2.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[12px] font-medium text-foreground">{opt.name}</span>
              <Money value={opt.estimated_monthly_cost_usd} compact inline className="text-[11px]" />
            </div>
            {opt.pros.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-[10.5px] text-mint" style={{ color: "var(--mint)" }}>
                {opt.pros.map((p, j) => (
                  <li key={j}>+ {p}</li>
                ))}
              </ul>
            )}
            {opt.cons.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-[10.5px]" style={{ color: "var(--ember)" }}>
                {opt.cons.map((c, j) => (
                  <li key={j}>− {c}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
