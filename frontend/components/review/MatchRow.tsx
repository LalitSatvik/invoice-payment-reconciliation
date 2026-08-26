"use client";

import { useState } from "react";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { MatchDetailOut } from "@/lib/types";

export interface MatchRowProps {
  match: MatchDetailOut;
  onAccept: (matchId: string) => Promise<void> | void;
  onReject: (matchId: string) => Promise<void> | void;
}

/** Confidence bands within `status=suggested` (rejected matches are deleted
 * server-side, so there is no third "rejected but visible" band). */
export function confidenceBand(score: number): "auto" | "review" {
  return score >= 85 ? "auto" : "review";
}

const bandVariant: Record<"auto" | "review", BadgeVariant> = {
  auto: "success",
  review: "warning",
};

const bandLabel: Record<"auto" | "review", string> = {
  auto: "Auto-suggested",
  review: "Needs review",
};

function formatAmount(amount: string, currency: string): string {
  const value = Number(amount);
  if (Number.isNaN(value)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value);
  } catch {
    return `${amount} ${currency}`;
  }
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

/**
 * Side-by-side card for one suggested match: invoice fields on the left,
 * payment fields on the right, the overall confidence score plus its three
 * component scores, and one-click Accept/Reject actions.
 */
export function MatchRow({ match, onAccept, onReject }: MatchRowProps) {
  const [pendingAction, setPendingAction] = useState<"accept" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const confidence = Number(match.confidence_score);
  const band = confidenceBand(confidence);

  async function handle(action: "accept" | "reject") {
    setPendingAction(action);
    setError(null);
    try {
      await (action === "accept" ? onAccept(match.id) : onReject(match.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not ${action} this match.`);
      setPendingAction(null);
    }
  }

  const busy = pendingAction !== null;

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge variant={bandVariant[band]}>{bandLabel[band]}</Badge>
          <span className="text-sm font-semibold tabular-nums">{confidence.toFixed(1)}% confidence</span>
        </div>
        <dl className="flex gap-4 text-xs text-text-muted">
          <div className="flex items-center gap-1">
            <dt>Amount</dt>
            <dd className="font-medium tabular-nums text-text">{Number(match.amount_score).toFixed(0)}</dd>
          </div>
          <div className="flex items-center gap-1">
            <dt>Date</dt>
            <dd className="font-medium tabular-nums text-text">{Number(match.date_score).toFixed(0)}</dd>
          </div>
          <div className="flex items-center gap-1">
            <dt>Reference</dt>
            <dd className="font-medium tabular-nums text-text">{Number(match.reference_score).toFixed(0)}</dd>
          </div>
        </dl>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2 rounded-sm border border-border p-4">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Invoice</span>
          <p className="text-sm font-semibold">{match.invoice.vendor_name ?? "Unknown vendor"}</p>
          <p className="text-sm tabular-nums">{formatAmount(match.invoice.amount, match.invoice.currency)}</p>
          <p className="text-sm text-text-muted">{formatDate(match.invoice.invoice_date)}</p>
          {match.invoice.invoice_number && (
            <p className="text-xs text-text-muted">Invoice #{match.invoice.invoice_number}</p>
          )}
          <p className="truncate text-xs text-text-muted" title={match.invoice.raw_reference_text ?? undefined}>
            Ref: {match.invoice.raw_reference_text ?? "-"}
          </p>
        </div>

        <div className="flex flex-col gap-2 rounded-sm border border-border p-4">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Payment</span>
          <p className="text-sm font-semibold">{match.payment.counterparty ?? "Unknown counterparty"}</p>
          <p className="text-sm tabular-nums">{formatAmount(match.payment.amount, match.payment.currency)}</p>
          <p className="text-sm text-text-muted">{formatDate(match.payment.payment_date)}</p>
          <p className="truncate text-xs text-text-muted" title={match.payment.reference ?? undefined}>
            Ref: {match.payment.reference ?? "-"}
          </p>
        </div>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="flex justify-end gap-3">
        <Button
          type="button"
          variant="secondary"
          disabled={busy}
          onClick={() => handle("reject")}
        >
          {pendingAction === "reject" ? "Rejecting..." : "Reject"}
        </Button>
        <Button type="button" disabled={busy} onClick={() => handle("accept")}>
          {pendingAction === "accept" ? "Accepting..." : "Accept"}
        </Button>
      </div>
    </Card>
  );
}
