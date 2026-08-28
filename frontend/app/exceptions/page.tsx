"use client";

import { useEffect, useState } from "react";
import { ApiError, listExceptions, resolveException } from "@/lib/api-client";
import type { ExceptionOut, ExceptionReason } from "@/lib/types";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PillNav } from "@/components/nav/PillNav";
import { ExceptionsIcon, ExportIcon, ReviewIcon, UploadIcon } from "@/components/nav/icons";

const navItems = [
  { href: "/", label: "Home", icon: <UploadIcon /> },
  { href: "/review", label: "Review", icon: <ReviewIcon /> },
  { href: "/exceptions", label: "Exceptions", icon: <ExceptionsIcon /> },
  { href: "/export", label: "Export", icon: <ExportIcon /> },
];

/** Readable labels for every reason the schema allows. In practice today the
 * engine only ever produces the first four; `possible_split_payment` and
 * `amount_mismatch_only` are schema placeholders for future engine work, and
 * `rejected_by_reviewer` is produced by `POST /matches/{id}/reject`. */
const reasonLabel: Record<ExceptionReason, string> = {
  no_candidate: "No candidate found",
  below_threshold: "Below confidence threshold",
  ambiguous_multiple_candidates: "Ambiguous - multiple candidates",
  candidate_claimed_elsewhere: "Candidate claimed elsewhere",
  possible_split_payment: "Possible split payment",
  rejected_by_reviewer: "Rejected by reviewer",
  amount_mismatch_only: "Amount mismatch only",
};

const reasonVariant: Record<ExceptionReason, BadgeVariant> = {
  no_candidate: "neutral",
  below_threshold: "warning",
  ambiguous_multiple_candidates: "accent",
  candidate_claimed_elsewhere: "accent",
  possible_split_payment: "warning",
  rejected_by_reviewer: "danger",
  amount_mismatch_only: "warning",
};

const REASON_FILTER_OPTIONS: (ExceptionReason | "all")[] = [
  "all",
  "no_candidate",
  "below_threshold",
  "ambiguous_multiple_candidates",
  "candidate_claimed_elsewhere",
  "possible_split_payment",
  "rejected_by_reviewer",
  "amount_mismatch_only",
];

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-US", { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}...` : id;
}

/**
 * One exception's card: reason, own-side reference, and (for the
 * candidate-bearing reasons) a candidate picker to resolve by linking, plus
 * a dismiss action available on any exception.
 *
 * Candidate display is id + confidence score only -- there is no dedicated
 * single-invoice/single-payment GET endpoint on the backend, and
 * `candidate_ids` names records that (for `ambiguous_multiple_candidates`
 * and `candidate_claimed_elsewhere`) generally never appear in any `Match`
 * row, so there is no existing endpoint to over-fetch full candidate detail
 * from either. Showing id + score is enough for the reviewer to pick the
 * best-scored candidate, which is what the brief asks for at minimum.
 */
function ExceptionCard({
  exception,
  onResolved,
}: {
  exception: ExceptionOut;
  onResolved: (id: string) => void;
}) {
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<"link" | "dismiss" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ownSideIsInvoice = exception.invoice_id !== null;
  // `below_threshold` belongs here alongside the two ambiguity reasons: the
  // engine ranks and stores a full candidate list for it too, and it is the
  // most common real-world near-miss (right amount and date, reference text
  // too weak to clear the threshold). Leaving it out made those dismiss-only,
  // even though `POST /exceptions/{id}/resolve` accepts linking any pair.
  const hasCandidates =
    (exception.reason === "ambiguous_multiple_candidates" ||
      exception.reason === "candidate_claimed_elsewhere" ||
      exception.reason === "below_threshold") &&
    exception.candidate_ids !== null &&
    exception.candidate_ids.length > 0;

  async function handleLink() {
    if (!selectedCandidate) return;
    setPending("link");
    setError(null);
    try {
      const payload = ownSideIsInvoice
        ? {
            link_invoice_id: exception.invoice_id!,
            link_payment_id: selectedCandidate,
            resolution_note: note || undefined,
          }
        : {
            link_invoice_id: selectedCandidate,
            link_payment_id: exception.payment_id!,
            resolution_note: note || undefined,
          };
      await resolveException(exception.id, payload);
      onResolved(exception.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resolve this exception.");
      setPending(null);
    }
  }

  async function handleDismiss() {
    setPending("dismiss");
    setError(null);
    try {
      await resolveException(exception.id, { dismiss: true, resolution_note: note || undefined });
      onResolved(exception.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not dismiss this exception.");
      setPending(null);
    }
  }

  const busy = pending !== null;

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge variant={reasonVariant[exception.reason]}>{reasonLabel[exception.reason]}</Badge>
          <span className="text-sm font-medium">
            {ownSideIsInvoice ? "Invoice" : "Payment"} {shortId((ownSideIsInvoice ? exception.invoice_id : exception.payment_id)!)}
          </span>
        </div>
        <span className="text-xs text-text-muted">Opened {formatTimestamp(exception.created_at)}</span>
      </div>

      {hasCandidates && (
        <div className="flex flex-col gap-2 rounded-sm border border-border p-4">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
            Candidate {ownSideIsInvoice ? "payments" : "invoices"} (best first)
          </span>
          <div className="flex flex-col gap-2">
            {exception.candidate_ids!.map((candidate) => (
              <label
                key={candidate.id}
                className="flex items-center justify-between gap-3 rounded-sm border border-border px-3 py-2 text-sm transition-colors hover:border-text/40 has-[:checked]:border-text has-[:checked]:bg-accent-soft"
              >
                <span className="flex items-center gap-2">
                  <input
                    type="radio"
                    name={`candidate-${exception.id}`}
                    value={candidate.id}
                    checked={selectedCandidate === candidate.id}
                    onChange={() => setSelectedCandidate(candidate.id)}
                  />
                  <span className="font-mono text-xs">{shortId(candidate.id)}</span>
                </span>
                <span className="tabular-nums text-text-muted">{candidate.confidence.toFixed(1)}%</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
          Resolution note (optional)
        </span>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Why this was resolved..."
          className="h-9 rounded-sm border border-border bg-surface px-3 text-sm"
        />
      </label>

      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="flex flex-wrap justify-end gap-3">
        <Button type="button" variant="secondary" disabled={busy} onClick={handleDismiss}>
          {pending === "dismiss" ? "Dismissing..." : "Dismiss"}
        </Button>
        {hasCandidates && (
          <Button type="button" disabled={busy || !selectedCandidate} onClick={handleLink}>
            {pending === "link" ? "Linking..." : "Link selected candidate"}
          </Button>
        )}
      </div>
    </Card>
  );
}

export default function ExceptionsPage() {
  const [exceptions, setExceptions] = useState<ExceptionOut[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reasonFilter, setReasonFilter] = useState<ExceptionReason | "all">("all");

  // Refetches whenever the reason filter changes. Every state update lives
  // inside a `.then`/`.catch`/`.finally` callback rather than synchronously
  // in the effect body -- the "loading" flag for a filter change is set by
  // the <select> handler below, which runs outside the effect.
  useEffect(() => {
    let cancelled = false;
    listExceptions({
      status: "open",
      reason: reasonFilter === "all" ? undefined : reasonFilter,
      limit: 200,
    })
      .then((result) => {
        if (cancelled) return;
        setExceptions(result.items);
        setTotal(result.total);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load exceptions.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reasonFilter]);

  function handleResolved(id: string) {
    setExceptions((prev) => prev.filter((e) => e.id !== id));
    setTotal((prev) => Math.max(0, prev - 1));
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-4">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Exceptions</span>
        <h1 className="text-3xl font-extrabold tracking-tight">Exceptions queue</h1>
        <PillNav items={navItems} activeHref="/exceptions" />
      </header>

      {error && (
        <Card className="border-danger/30 bg-danger-bg">
          <p className="text-sm text-danger">{error}</p>
        </Card>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-text-muted">Reason</span>
          <select
            value={reasonFilter}
            onChange={(e) => {
              setLoading(true);
              setReasonFilter(e.target.value as ExceptionReason | "all");
            }}
            className="h-9 rounded-sm border border-border bg-surface px-3 text-sm"
          >
            <option value="all">All reasons</option>
            {REASON_FILTER_OPTIONS.filter((r) => r !== "all").map((reason) => (
              <option key={reason} value={reason}>
                {reasonLabel[reason as ExceptionReason]}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-text-muted">
          {exceptions.length} shown{total > exceptions.length ? ` of ${total} total open` : ""}
        </span>
      </div>

      {loading && (
        <Card>
          <p className="text-sm text-text-muted">Loading exceptions...</p>
        </Card>
      )}

      {!loading && exceptions.length === 0 && !error && (
        <Card>
          <p className="text-sm text-text-muted">No open exceptions for this filter.</p>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        {exceptions.map((exception) => (
          <ExceptionCard key={exception.id} exception={exception} onResolved={handleResolved} />
        ))}
      </div>
    </div>
  );
}
