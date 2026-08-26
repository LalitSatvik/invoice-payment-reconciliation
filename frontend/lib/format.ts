/**
 * Shared display-formatting helpers for values coming back from the
 * backend -- Decimal-as-string amounts and ISO timestamps.
 */

/** Formats a Decimal-as-string amount as USD currency. Falls back to the
 * raw string if it isn't a parseable number, so a malformed value never
 * renders as "$NaN". */
export function formatCurrency(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}
