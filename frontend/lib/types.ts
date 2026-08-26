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
