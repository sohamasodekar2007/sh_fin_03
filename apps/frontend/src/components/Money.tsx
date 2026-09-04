import { formatCurrency, isNum, NOT_AVAILABLE } from "@/lib/format";

/**
 * Every monetary figure in this app renders as USD primary with an INR
 * subscript beneath — this is the one place that pairing is built, so
 * every KPI, table cell, chart tooltip and waterfall label goes through
 * it. The API returns USD only; INR is always computed client-side from
 * NEXT_PUBLIC_USD_TO_INR, never requested from the backend.
 *
 * Indian digit grouping is 2,2,3 (₹3,55,323), not the 3,3,3 a naive
 * toLocaleString would produce (₹355,323) — Intl.NumberFormat('en-IN')
 * gets this right, which is why formatInr below exists instead of a
 * hand-rolled string.
 */

const USD_TO_INR = Number(process.env.NEXT_PUBLIC_USD_TO_INR) || 83;

const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export function formatInr(usd: number): string {
  return inrFormatter.format(usd * USD_TO_INR);
}

/**
 * Plain-string variant for contexts a React component can't render into —
 * SVG <text>/<tspan> nodes (Sankey node labels, waterfall bars, chart
 * tooltips built as raw SVG). Same NOT_AVAILABLE discipline as <Money/>.
 */
export function formatMoneyParts(
  value: number | null | undefined,
  opts: { compact?: boolean; cents?: boolean } = {},
): { usd: string; inr: string | null } {
  if (!isNum(value)) return { usd: NOT_AVAILABLE, inr: null };
  return { usd: formatCurrency(value, opts), inr: formatInr(value) };
}

interface MoneyProps {
  value: number | null | undefined;
  compact?: boolean;
  cents?: boolean;
  className?: string;
  /** USD and INR on one line ("$4,281 (₹3,55,323)") instead of stacked —
   * for dense contexts like table cells where a second line would break
   * row height. */
  inline?: boolean;
  /** Suppress the INR subscript entirely — rare, for places already tight
   * on space where the primary Money elsewhere on the same row/card
   * already carries it (e.g. a delta figure next to the headline). */
  usdOnly?: boolean;
  /** Color/etc. for the primary USD line only — the INR subscript always
   * stays --ink-faint regardless, so it reads as secondary everywhere. */
  style?: React.CSSProperties;
}

export function Money({ value, compact, cents, className = "", inline = false, usdOnly = false, style }: MoneyProps) {
  if (!isNum(value)) {
    return (
      <span className={`num ${className}`} style={style}>
        {NOT_AVAILABLE}
      </span>
    );
  }

  const usd = formatCurrency(value, { compact, cents });
  if (usdOnly) {
    return (
      <span className={`num ${className}`} style={style}>
        {usd}
      </span>
    );
  }

  const inr = formatInr(value);
  if (inline) {
    return (
      <span className={`num ${className}`} style={style}>
        {usd} <span className="text-ink-faint">({inr})</span>
      </span>
    );
  }

  return (
    <span className={`num inline-flex flex-col ${className}`}>
      <span style={style}>{usd}</span>
      <span className="text-[0.7em] leading-tight text-ink-faint">{inr}</span>
    </span>
  );
}
