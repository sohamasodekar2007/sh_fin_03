import type { FindingCard } from "@/lib/cloudcare-data";

export function FindingCardView({ card }: { card: FindingCard }) {
  const evidenceEntries = Object.entries(card.evidence);
  return (
    <div className="mt-2 rounded-md border border-border/70 bg-surface-raised/60 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{card.rule_id}</span>
        <span className="num text-[10.5px] text-ink-faint">{card.resource_id}</span>
      </div>
      <p className="mt-1.5 text-[12.5px] leading-relaxed text-foreground/85">{card.summary}</p>
      {evidenceEntries.length > 0 && (
        <div className="mt-2.5 divide-y divide-border/60">
          {evidenceEntries.map(([key, value]) => (
            <div key={key} className="flex items-baseline justify-between gap-4 py-1.5">
              <span className="text-[11.5px] text-ink-dim">{key}</span>
              <span className="num text-[11px] text-ink-faint">{String(value)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
