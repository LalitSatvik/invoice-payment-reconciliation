/**
 * TypeScript mirrors of the backend's Pydantic response/request shapes
 * (see `backend/app/schemas/*.py`). Keep in sync by hand -- there is no
 * codegen step between the two.
 */

/** Response for `POST /api/v1/uploads/preview`. */
export interface PreviewResponse {
  headers: string[];
  /** Positional: one value per header, in header order. */
  sample_rows: string[][];
}

export type UploadKind = "invoice_pdf" | "invoice_csv" | "bank_csv";
export type UploadStatus = "pending" | "processing" | "completed" | "failed";

export interface UploadBatchOut {
  id: string;
  kind: UploadKind;
  original_filename: string;
  status: UploadStatus;
  row_count: number | null;
  error_summary: string | null;
  source_mapping_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export type TargetKind = "invoice" | "payment";

/** Canonical column-map keys, keyed by `target_kind`. `date` and `amount`
 * are the only fields the backend requires; everything else is optional. */
export const CANONICAL_FIELDS: Record<
  TargetKind,
  { field: string; label: string; required: boolean }[]
> = {
  invoice: [
    { field: "date", label: "Invoice date", required: true },
    { field: "amount", label: "Amount", required: true },
    { field: "invoice_number", label: "Invoice number", required: false },
    { field: "vendor_name", label: "Vendor name", required: false },
    { field: "due_date", label: "Due date", required: false },
    { field: "raw_reference_text", label: "Reference text", required: false },
  ],
  payment: [
    { field: "date", label: "Payment date", required: true },
    { field: "amount", label: "Amount", required: true },
    { field: "reference", label: "Reference", required: false },
    { field: "counterparty", label: "Counterparty", required: false },
  ],
};

export interface SourceMappingOut {
  id: string;
  source_name: string;
  target_kind: TargetKind;
  column_map: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface SourceMappingCreate {
  source_name: string;
  target_kind: TargetKind;
  column_map: Record<string, string>;
}

export interface MatchedTotals {
  count: number;
  amount: string;
}

export interface UnmatchedSideTotals {
  count: number;
  amount: string;
}

export interface UnmatchedTotals {
  invoices: UnmatchedSideTotals;
  payments: UnmatchedSideTotals;
}

export interface ExceptionReasonTotals {
  count: number;
  amount: string | null;
}

export interface ExportSummaryResponse {
  generated_at: string;
  matched: MatchedTotals;
  unmatched: UnmatchedTotals;
  exceptions_by_reason: Record<string, ExceptionReasonTotals>;
}

/** Standard FastAPI error body: `{"detail": "..."}` (or a validation list). */
export interface ApiErrorBody {
  detail?: string | { msg: string }[];
}

// ---------------------------------------------------------------------------
// Matching / match review
// ---------------------------------------------------------------------------

export type MatchStatus = "suggested" | "accepted" | "rejected";

export interface MatchingRunRequest {
  batch_ids?: string[] | null;
}

export interface MatchingRunResponse {
  matches_created: number;
  exceptions_created: number;
}

/** Mirrors the backend's `InvoiceSummary` (see `app/schemas/match.py`). */
export interface InvoiceSummary {
  id: string;
  upload_batch_id: string;
  invoice_number: string | null;
  vendor_name: string | null;
  invoice_date: string;
  due_date: string | null;
  amount: string;
  currency: string;
  raw_reference_text: string | null;
  status: string;
}

/** Mirrors the backend's `PaymentSummary`. */
export interface PaymentSummary {
  id: string;
  upload_batch_id: string;
  payment_date: string;
  amount: string;
  currency: string;
  reference: string | null;
  counterparty: string | null;
  status: string;
}

/** All score fields are Decimal-as-string on a 0-100 scale. */
export interface MatchOut {
  id: string;
  invoice_id: string;
  payment_id: string;
  confidence_score: string;
  amount_score: string;
  date_score: string;
  reference_score: string;
  match_status: MatchStatus;
  suggested_at: string;
  reviewed_at: string | null;
  reviewer_note: string | null;
}

export interface MatchDetailOut extends MatchOut {
  invoice: InvoiceSummary;
  payment: PaymentSummary;
}

export interface MatchListResponse {
  items: MatchOut[];
  total: number;
  limit: number;
  offset: number;
}

// ---------------------------------------------------------------------------
// Exceptions
// ---------------------------------------------------------------------------

export type ExceptionStatus = "open" | "resolved";

export type ExceptionReason =
  | "no_candidate"
  | "below_threshold"
  | "ambiguous_multiple_candidates"
  | "candidate_claimed_elsewhere"
  | "possible_split_payment"
  | "rejected_by_reviewer"
  | "amount_mismatch_only";

/** One entry of `ExceptionOut.candidate_ids`: an opposite-side record id
 * plus the confidence score it scored against the exception's own record. */
export interface ExceptionCandidate {
  id: string;
  confidence: number;
}

export interface ExceptionOut {
  id: string;
  invoice_id: string | null;
  payment_id: string | null;
  reason: ExceptionReason;
  candidate_ids: ExceptionCandidate[] | null;
  status: ExceptionStatus;
  resolution_note: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ExceptionListResponse {
  items: ExceptionOut[];
  total: number;
  limit: number;
  offset: number;
}

/** Body for `POST /exceptions/{id}/resolve` -- exactly one mode: link
 * (`link_invoice_id` + `link_payment_id`) or dismiss (`dismiss: true`). */
export interface ExceptionResolveRequest {
  link_invoice_id?: string;
  link_payment_id?: string;
  dismiss?: boolean;
  resolution_note?: string;
}
