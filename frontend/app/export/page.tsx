"use client";

import { useEffect, useState } from "react";
import { ApiError, getExportSummary, getReconciliationCsvUrl } from "@/lib/api-client";
import type { ExportSummaryResponse } from "@/lib/types";
import { formatCurrency } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { KpiStat } from "@/components/ui/KpiStat";
import { PillNav } from "@/components/nav/PillNav";
import { ExceptionsIcon, ExportIcon, ReviewIcon, UploadIcon } from "@/components/nav/icons";

const navItems = [
  { href: "/", label: "Home", icon: <UploadIcon /> },
  { href: "/review", label: "Review", icon: <ReviewIcon /> },
  { href: "/exceptions", label: "Exceptions", icon: <ExceptionsIcon /> },
  { href: "/export", label: "Export", icon: <ExportIcon /> },
];

/** Readable labels for the reasons the schema documents today. Any other
 * key `exceptions_by_reason` reports -- there is no guarantee the backend
 * only ever sends these seven -- falls through to a generic
 * underscore-to-title-case conversion below, so the page never silently
 * drops a reason it doesn't recognize. */
const KNOWN_REASON_LABELS: Record<string, string> = {
  no_candidate: "No candidate found",
  below_threshold: "Below confidence threshold",
  ambiguous_multiple_candidates: "Ambiguous - multiple candidates",
  candidate_claimed_elsewhere: "Candidate claimed elsewhere",
  possible_split_payment: "Possible split payment",
  rejected_by_reviewer: "Rejected by reviewer",
  amount_mismatch_only: "Amount mismatch only",
};

function reasonLabel(reason: string): string {
  const known = KNOWN_REASON_LABELS[reason];
  if (known) return known;
  return reason
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function ExportPage() {
  const [summary, setSummary] = useState<ExportSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getExportSummary()
      .then((result) => {
        setSummary(result);
        setError(null);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not load the export summary."),
      )
      .finally(() => setLoading(false));
  }, []);

  const reasonEntries = summary ? Object.entries(summary.exceptions_by_reason) : [];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-6 py-12">
      <header className="flex flex-col gap-4">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
          Reconciliation tool
        </span>
        <h1 className="text-3xl font-extrabold tracking-tight">Export</h1>
        <PillNav items={navItems} activeHref="/export" />
      </header>

      {loading && (
        <Card>
          <p className="text-sm text-text-muted">Loading export summary...</p>
        </Card>
      )}

      {error && (
        <Card className="border-danger/30 bg-danger-bg">
          <p className="text-sm text-danger">{error}</p>
        </Card>
      )}

      {summary && (
        <>
          <section className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold tracking-tight">Summary</h2>
              <span className="text-xs text-text-muted">
                Generated {formatTimestamp(summary.generated_at)}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Card>
                <KpiStat
                  label="Matched"
                  value={summary.matched.count}
                  delta={formatCurrency(summary.matched.amount)}
                  deltaTone="positive"
                />
              </Card>
              <Card>
                <KpiStat
                  label="Unmatched invoices"
                  value={summary.unmatched.invoices.count}
                  delta={formatCurrency(summary.unmatched.invoices.amount)}
                  deltaTone="negative"
                />
              </Card>
              <Card>
                <KpiStat
                  label="Unmatched payments"
                  value={summary.unmatched.payments.count}
                  delta={formatCurrency(summary.unmatched.payments.amount)}
                  deltaTone="negative"
                />
              </Card>
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <h2 className="text-lg font-semibold tracking-tight">Exceptions by reason</h2>
            {reasonEntries.length === 0 ? (
              <Card>
                <p className="text-sm text-text-muted">No exceptions recorded.</p>
              </Card>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {reasonEntries.map(([reason, totals]) => (
                  <Card key={reason}>
                    <KpiStat
                      label={reasonLabel(reason)}
                      value={totals.count}
                      delta={totals.amount !== null ? formatCurrency(totals.amount) : "—"}
                      deltaTone="neutral"
                    />
                  </Card>
                ))}
              </div>
            )}
          </section>

          <section className="flex flex-col gap-4">
            <h2 className="text-lg font-semibold tracking-tight">Download</h2>
            <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium">Reconciliation CSV</p>
                <p className="text-sm text-text-muted">
                  One row per accepted match, with invoice, payment, and score fields.
                </p>
              </div>
              <a href={getReconciliationCsvUrl()}>
                <Button type="button">Download CSV</Button>
              </a>
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
