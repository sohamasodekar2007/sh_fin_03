/**
 * Generic currency/percentage formatting, extracted from the template's
 * src/data/finance-data.ts (Phase 8) — that file is the template's own
 * fictional CFO dataset, which this phase deliberately does not port
 * ("before any CloudCare content exists"). KpiStrip.tsx only needed four
 * pure formatting functions from it (NOT_AVAILABLE, isNum, formatCurrency,
 * fmtPct); everything else in finance-data.ts is business data, not part
 * of this scaffold. Locale/currency are fixed to en-US/USD here rather than
 * read from a BRAND config — there is no BRAND config yet.
 *
 * Phase 10 adds safeDiv — same discipline: a ratio with a zero or
 * non-finite denominator is not computable, not zero, so every caller
 * (delta percentages, ribbon shares) gets null instead of NaN or Infinity.
 * Never render NaN.
 */

const LOCALE = "en-US";
const CURRENCY = "USD";

/** Neutral placeholder for a figure that is not computable. */
export const NOT_AVAILABLE = "—";

/** True when a value is a real, printable number. */
export function isNum(v: number | null | undefined): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** Division that is null (not NaN, not Infinity) when it isn't computable. */
export function safeDiv(numerator: number, denominator: number): number | null {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator)) return null;
  if (denominator === 0) return null;
  const r = numerator / denominator;
  return Number.isFinite(r) ? r : null;
}

const currencyFormatter = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: CURRENCY,
});

/**
 * Symbol placement is read from the locale rather than assumed: en-US prints
 * "$1,234" while de-DE prints "1.234 €", including the non-breaking space.
 */
const SYMBOL_LAYOUT = (() => {
  const parts = currencyFormatter.formatToParts(1234.56);
  const ci = parts.findIndex((p) => p.type === "currency");
  const symbol = ci >= 0 ? parts[ci].value : "";
  if (ci < 0) return { symbol: "", prefix: true, gap: "" };
  const before = parts.slice(0, ci).every((p) => p.type === "literal");
  const gap = before
    ? parts[ci + 1]?.type === "literal"
      ? parts[ci + 1].value
      : ""
    : parts[ci - 1]?.type === "literal"
      ? parts[ci - 1].value
      : "";
  return { symbol, prefix: before, gap };
})();

function withSymbol(body: string): string {
  const { symbol, prefix, gap } = SYMBOL_LAYOUT;
  return prefix ? `${symbol}${gap}${body}` : `${body}${gap}${symbol}`;
}

const wholeFormatter = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const centsFormatter = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatCurrency(n: number, opts: { compact?: boolean; cents?: boolean } = {}): string {
  if (!Number.isFinite(n)) return NOT_AVAILABLE;
  const abs = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (opts.compact) {
    if (abs >= 1_000_000) return `${sign}${withSymbol(`${centsFormatter.format(abs / 1_000_000)}M`)}`;
    if (abs >= 1_000) return `${sign}${withSymbol(`${wholeFormatter.format(abs / 1_000)}K`)}`;
    return `${sign}${withSymbol(wholeFormatter.format(abs))}`;
  }
  const body = opts.cents ? centsFormatter.format(abs) : wholeFormatter.format(abs);
  return `${sign}${withSymbol(body)}`;
}

/** Currency, or the neutral placeholder when the figure is not computable. */
export function formatCurrencyOr(n: number | null | undefined, opts: { compact?: boolean; cents?: boolean } = {}): string {
  return isNum(n) ? formatCurrency(n, opts) : NOT_AVAILABLE;
}

export function fmtPct(n: number, digits = 1): string {
  if (!Number.isFinite(n)) return NOT_AVAILABLE;
  return `${new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n * 100)}%`;
}

/** Percentage, or the neutral placeholder when the ratio is not computable. */
export function fmtPctOr(n: number | null | undefined, digits = 1): string {
  return isNum(n) ? fmtPct(n, digits) : NOT_AVAILABLE;
}
