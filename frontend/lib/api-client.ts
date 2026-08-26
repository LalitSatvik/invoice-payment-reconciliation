/**
 * Typed fetch wrapper for the backend's `/api/v1` endpoints (see
 * `backend/app/api/routes/*.py` for the source of truth). Base URL comes
 * from `NEXT_PUBLIC_API_URL` so it can point at a different backend in
 * different environments without a rebuild-time config file.
 */
import type {
  ExceptionListResponse,
  ExceptionOut,
  ExceptionResolveRequest,
  ExportSummaryResponse,
  MatchDetailOut,
  MatchingRunRequest,
  MatchingRunResponse,
  MatchListResponse,
  MatchOut,
  MatchStatus,
  PreviewResponse,
  SourceMappingCreate,
  SourceMappingOut,
  TargetKind,
  UploadBatchOut,
} from "@/lib/types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

/** Thrown for any non-2xx response; carries the parsed `detail` when present. */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function extractDetail(body: unknown): string | undefined {
  if (!body || typeof body !== "object" || !("detail" in body)) return undefined;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : String(item)))
      .join("; ");
  }
  return undefined;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Could not reach the backend at ${API_BASE_URL}. Is it running?`);
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      detail = extractDetail(await response.json());
    } catch {
      // Response body wasn't JSON -- fall through to the generic message below.
    }
    throw new ApiError(response.status, detail ?? `Request failed with status ${response.status}`);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function jsonHeaders(): HeadersInit {
  return { "Content-Type": "application/json" };
}

// ---------------------------------------------------------------------------
// Uploads
// ---------------------------------------------------------------------------

export function previewUpload(file: File): Promise<PreviewResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<PreviewResponse>("/api/v1/uploads/preview", { method: "POST", body: form });
}

export function uploadInvoices(file: File, sourceMappingId?: string): Promise<UploadBatchOut> {
  const form = new FormData();
  form.append("file", file);
  if (sourceMappingId) form.append("source_mapping_id", sourceMappingId);
  return request<UploadBatchOut>("/api/v1/uploads/invoices", { method: "POST", body: form });
}

export function uploadBankStatement(file: File, sourceMappingId: string): Promise<UploadBatchOut> {
  const form = new FormData();
  form.append("file", file);
  form.append("source_mapping_id", sourceMappingId);
  return request<UploadBatchOut>("/api/v1/uploads/bank-statement", { method: "POST", body: form });
}

export function getUploadBatch(batchId: string): Promise<UploadBatchOut> {
  return request<UploadBatchOut>(`/api/v1/uploads/${batchId}`);
}

// ---------------------------------------------------------------------------
// Source mappings
// ---------------------------------------------------------------------------

export function listMappings(targetKind?: TargetKind): Promise<SourceMappingOut[]> {
  return request<SourceMappingOut[]>("/api/v1/mappings").then((mappings) =>
    targetKind ? mappings.filter((mapping) => mapping.target_kind === targetKind) : mappings,
  );
}

export function createMapping(payload: SourceMappingCreate): Promise<SourceMappingOut> {
  return request<SourceMappingOut>("/api/v1/mappings", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });
}

export function getMapping(mappingId: string): Promise<SourceMappingOut> {
  return request<SourceMappingOut>(`/api/v1/mappings/${mappingId}`);
}

export function updateMapping(
  mappingId: string,
  payload: SourceMappingCreate,
): Promise<SourceMappingOut> {
  return request<SourceMappingOut>(`/api/v1/mappings/${mappingId}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Export summary
// ---------------------------------------------------------------------------

export function getExportSummary(): Promise<ExportSummaryResponse> {
  return request<ExportSummaryResponse>("/api/v1/export/summary");
}

// ---------------------------------------------------------------------------
// Matching / match review
// ---------------------------------------------------------------------------

export function runMatching(payload: MatchingRunRequest = {}): Promise<MatchingRunResponse> {
  return request<MatchingRunResponse>("/api/v1/matching/run", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });
}

export interface ListMatchesParams {
  status?: MatchStatus;
  minConfidence?: number;
  maxConfidence?: number;
  limit?: number;
  offset?: number;
}

export function listMatches(params: ListMatchesParams = {}): Promise<MatchListResponse> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.minConfidence !== undefined) query.set("min_confidence", String(params.minConfidence));
  if (params.maxConfidence !== undefined) query.set("max_confidence", String(params.maxConfidence));
  query.set("limit", String(params.limit ?? 200));
  query.set("offset", String(params.offset ?? 0));
  return request<MatchListResponse>(`/api/v1/matches?${query.toString()}`);
}

export function getMatch(matchId: string): Promise<MatchDetailOut> {
  return request<MatchDetailOut>(`/api/v1/matches/${matchId}`);
}

export function acceptMatch(matchId: string): Promise<MatchOut> {
  return request<MatchOut>(`/api/v1/matches/${matchId}/accept`, { method: "POST" });
}

export function rejectMatch(matchId: string): Promise<MatchOut> {
  return request<MatchOut>(`/api/v1/matches/${matchId}/reject`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Exceptions
// ---------------------------------------------------------------------------

export interface ListExceptionsParams {
  status?: "open" | "resolved";
  reason?: string;
  limit?: number;
  offset?: number;
}

export function listExceptions(params: ListExceptionsParams = {}): Promise<ExceptionListResponse> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.reason) query.set("reason", params.reason);
  query.set("limit", String(params.limit ?? 200));
  query.set("offset", String(params.offset ?? 0));
  return request<ExceptionListResponse>(`/api/v1/exceptions?${query.toString()}`);
}

export function resolveException(
  exceptionId: string,
  payload: ExceptionResolveRequest,
): Promise<ExceptionOut> {
  return request<ExceptionOut>(`/api/v1/exceptions/${exceptionId}/resolve`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });
}
