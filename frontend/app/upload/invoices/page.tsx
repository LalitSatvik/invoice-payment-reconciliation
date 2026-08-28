"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ApiError, previewUpload, uploadInvoices } from "@/lib/api-client";
import type { PreviewResponse, UploadBatchOut } from "@/lib/types";
import { ColumnMappingTable } from "@/components/mapping/ColumnMappingTable";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PillNav } from "@/components/nav/PillNav";
import {
  BankIcon,
  ExceptionsIcon,
  ExportIcon,
  InvoiceIcon,
  ReviewIcon,
  UploadIcon,
} from "@/components/nav/icons";

// The two upload routes are listed here (and on the bank-statement page) so
// the nav can mark the page you are actually on. Without them, every upload
// page had to claim `activeHref="/"` and highlighted "Home" instead.
const navItems = [
  { href: "/", label: "Home", icon: <UploadIcon /> },
  { href: "/upload/invoices", label: "Upload invoices", icon: <InvoiceIcon /> },
  { href: "/upload/bank-statement", label: "Upload bank statement", icon: <BankIcon /> },
  { href: "/review", label: "Review", icon: <ReviewIcon /> },
  { href: "/exceptions", label: "Exceptions", icon: <ExceptionsIcon /> },
  { href: "/export", label: "Export", icon: <ExportIcon /> },
];

type Stage = "picking" | "mapping" | "submitting" | "done";

const statusVariant: Record<UploadBatchOut["status"], BadgeVariant> = {
  pending: "neutral",
  processing: "warning",
  completed: "success",
  failed: "danger",
};

function isPdf(file: File): boolean {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

export default function InvoiceUploadPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<Stage>("picking");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [mappingId, setMappingId] = useState<string | null>(null);
  const [batch, setBatch] = useState<UploadBatchOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setStage("picking");
    setFile(null);
    setPreview(null);
    setMappingId(null);
    setBatch(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setError(null);
    setFile(selected);

    if (isPdf(selected)) {
      // PDFs skip the mapping step entirely -- upload directly.
      await submitUpload(selected, undefined);
      return;
    }

    setStage("mapping");
    try {
      const result = await previewUpload(selected);
      setPreview(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not preview this file.");
      setStage("picking");
    }
  }

  async function submitUpload(fileToSubmit: File, sourceMappingId: string | undefined) {
    setStage("submitting");
    setError(null);
    try {
      const result = await uploadInvoices(fileToSubmit, sourceMappingId);
      setBatch(result);
      setStage("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
      setStage(sourceMappingId ? "mapping" : "picking");
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-4">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Upload</span>
        <h1 className="text-3xl font-extrabold tracking-tight">Invoices</h1>
        <PillNav items={navItems} activeHref="/upload/invoices" />
      </header>

      <Card className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Choose a file</h2>
          <p className="text-sm text-text-muted">
            PDF invoices upload immediately. CSV files go through a column-mapping step first.
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.csv,application/pdf,text/csv"
          onChange={handleFileChange}
          disabled={stage === "submitting"}
          className="text-sm file:mr-4 file:h-11 file:rounded-pill file:border-0 file:bg-accent file:px-5 file:text-sm file:font-semibold file:text-text file:transition-colors hover:file:bg-accent-hover active:file:bg-accent-active"
        />
        {file && <p className="text-sm text-text-muted">Selected: {file.name}</p>}
      </Card>

      {error && (
        <Card className="border-danger/30 bg-danger-bg">
          <p className="text-sm text-danger">{error}</p>
        </Card>
      )}

      {stage === "mapping" && preview && (
        <>
          <ColumnMappingTable
            targetKind="invoice"
            headers={preview.headers}
            sampleRows={preview.sample_rows}
            onMappingChange={setMappingId}
          />
          <div className="flex justify-end">
            <Button
              type="button"
              disabled={!mappingId || !file}
              onClick={() => file && mappingId && submitUpload(file, mappingId)}
            >
              Upload invoices
            </Button>
          </div>
        </>
      )}

      {stage === "submitting" && (
        <Card>
          <p className="text-sm text-text-muted">Uploading...</p>
        </Card>
      )}

      {stage === "done" && batch && (
        <Card className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold tracking-tight">Upload result</h2>
            <Badge variant={statusVariant[batch.status]}>{batch.status}</Badge>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs uppercase tracking-wide text-text-muted">Filename</dt>
              <dd className="font-medium">{batch.original_filename}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-text-muted">Kind</dt>
              <dd className="font-medium">{batch.kind}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-text-muted">Rows</dt>
              <dd className="font-medium tabular-nums">{batch.row_count ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-text-muted">Batch ID</dt>
              <dd className="truncate font-mono text-xs">{batch.id}</dd>
            </div>
          </dl>
          {batch.error_summary && (
            <p className="text-sm text-danger">{batch.error_summary}</p>
          )}
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="secondary" onClick={reset}>
              Upload another
            </Button>
            <Link href="/">
              <Button type="button">Back to dashboard</Button>
            </Link>
          </div>
        </Card>
      )}
    </div>
  );
}
