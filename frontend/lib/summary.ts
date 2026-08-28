/**
 * Shared read helpers for `GET /export/summary`, used by both the dashboard
 * (`app/page.tsx`) and the export page (`app/export/page.tsx`). Previously
 * each page carried its own copy of `isEmptySummary`, which meant every
 * change to what "empty" means had to be made twice.
 */
import type { ExportSummaryResponse } from "@/lib/types";

/**
 * True once a summary has loaded but there is genuinely nothing in it --
 * no accepted matches, nothing awaiting review, and no unmatched records on
 * either side. That only happens before anything has been uploaded, so both
 * pages give it its own message rather than a row of zero-value KPI cards
 * that could be mistaken for a stuck loading state or a quiet error.
 *
 * `in_review` has to be part of the check: a run that suggested matches but
 * has not been reviewed yet leaves both linked records out of the unmatched
 * pool and out of the accepted-match pool, so a summary that looks at only
 * those two buckets would call a freshly-matched dataset "empty".
 */
export function isEmptySummary(summary: ExportSummaryResponse): boolean {
  return (
    summary.matched.count === 0 &&
    summary.in_review.count === 0 &&
    summary.unmatched.invoices.count === 0 &&
    summary.unmatched.payments.count === 0
  );
}
