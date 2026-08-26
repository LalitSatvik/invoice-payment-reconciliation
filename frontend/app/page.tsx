"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getExportSummary } from "@/lib/api-client";
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

/** True once a summary has loaded but there is nothing in it yet -- no
 * matches, no unmatched invoices, no unmatched payments. That only happens
 * before anything has been uploaded, so it gets its own message rather than
 * three zero-value KPI cards that could otherwise be mistaken for a stuck
 * loading state or a quiet error. */
function isEmptySummary(summary: ExportSummaryResponse): boolean {
  return (
    summary.matched.count === 0 &&
    summary.unmatched.invoices.count === 0 &&
    summary.unmatched.payments.count === 0
  );
}

export default function Home() {
  const [summary, setSummary] = useState<ExportSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getExportSummary()
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load summary."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-6 py-12">
      <header className="flex flex-col gap-4">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
          Reconciliation tool
        </span>
        <h1 className="text-3xl font-extrabold tracking-tight">Dashboard</h1>
        <PillNav items={navItems} activeHref="/" />
      </header>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">Status</h2>
        {loading && (
          <Card>
            <p className="text-sm text-text-muted">Loading summary...</p>
          </Card>
        )}
        {error && (
          <Card className="bg-danger-bg">
            <p className="text-sm text-danger">{error}</p>
            <p className="text-xs text-text-muted">
              Upload some invoices and a bank statement to populate this dashboard.
            </p>
          </Card>
        )}
        {summary && isEmptySummary(summary) && (
          <Card>
            <p className="text-sm font-medium">No data yet.</p>
            <p className="text-sm text-text-muted">
              Upload invoices and a bank statement below to get started.
            </p>
          </Card>
        )}

        {summary && !isEmptySummary(summary) && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <KpiStat label="Matched" value={summary.matched.count} delta={formatCurrency(summary.matched.amount)} />
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
        )}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">Upload</h2>
        <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium">Invoices</p>
            <p className="text-sm text-text-muted">Upload PDF or CSV invoices.</p>
          </div>
          <Link href="/upload/invoices">
            <Button type="button">Upload invoices</Button>
          </Link>
        </Card>
        <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium">Bank statement</p>
            <p className="text-sm text-text-muted">Upload a CSV bank statement.</p>
          </div>
          <Link href="/upload/bank-statement">
            <Button type="button">Upload bank statement</Button>
          </Link>
        </Card>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">Next steps</h2>
        <Card className="flex flex-wrap gap-3">
          <Link href="/review">
            <Button type="button" variant="secondary">
              Review matches
            </Button>
          </Link>
          <Link href="/exceptions">
            <Button type="button" variant="secondary">
              Exceptions
            </Button>
          </Link>
          <Link href="/export">
            <Button type="button" variant="secondary">
              Export
            </Button>
          </Link>
        </Card>
      </section>
    </div>
  );
}
