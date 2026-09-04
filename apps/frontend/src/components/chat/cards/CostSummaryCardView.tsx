import { Money } from "@/components/Money";
import type { CostSummaryCard } from "@/lib/cloudcare-data";

export function CostSummaryCardView({ card }: { card: CostSummaryCard }) {
  return (
    <div className="mt-2 rounded-md border border-border/70 bg-surface-raised/60 p-3.5">
      <div className="eyebrow">Cost summary · trailing {card.period_days}d</div>
      <Money value={card.total_cost_usd} compact className="mt-1.5 text-lg font-medium" />
      {card.top_services.length > 0 && (
        <div className="mt-2.5 divide-y divide-border/60">
          {card.top_services.map((s, i) => (
            <div key={i} className="flex items-baseline justify-between gap-4 py-1.5">
              <span className="truncate text-[11.5px] text-ink-dim">{String(s.service_name ?? "—")}</span>
              <Money value={typeof s.cost_usd === "number" ? s.cost_usd : null} compact inline className="text-[11px]" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
