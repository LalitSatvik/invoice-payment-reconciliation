"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, createMapping, listMappings } from "@/lib/api-client";
import { CANONICAL_FIELDS, type SourceMappingOut, type TargetKind } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export interface ColumnMappingTableProps {
  targetKind: TargetKind;
  headers: string[];
  sampleRows: string[][];
  /** Fires with a persisted mapping id once one is ready to submit, or
   * `null` when the user has backed out of a ready state (e.g. switched
   * away from a previously-selected saved mapping). */
  onMappingChange: (mappingId: string | null) => void;
}

const UNMAPPED = "";

/**
 * Column-mapping step shown after `/uploads/preview`. Lets the user either
 * pick a previously-saved mapping for this `targetKind` outright, or map
 * each canonical field to a detected header by hand and save the result
 * under a new source name.
 */
export function ColumnMappingTable({
  targetKind,
  headers,
  sampleRows,
  onMappingChange,
}: ColumnMappingTableProps) {
  const canonicalFields = CANONICAL_FIELDS[targetKind];

  const [savedMappings, setSavedMappings] = useState<SourceMappingOut[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(true);
  const [selectedSavedId, setSelectedSavedId] = useState<string>("");

  const [fieldMap, setFieldMap] = useState<Record<string, string>>({});
  const [sourceName, setSourceName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listMappings(targetKind)
      .then((mappings) => {
        if (!cancelled) setSavedMappings(mappings);
      })
      .catch(() => {
        if (!cancelled) setSavedMappings([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingSaved(false);
      });
    return () => {
      cancelled = true;
    };
  }, [targetKind]);

  const requiredMissing = useMemo(
    () => canonicalFields.filter((f) => f.required && !fieldMap[f.field]),
    [canonicalFields, fieldMap],
  );
  const canSaveNewMapping = requiredMissing.length === 0 && sourceName.trim().length > 0;

  function handleFieldChange(field: string, header: string) {
    setFieldMap((prev) => {
      const next = { ...prev };
      if (header === UNMAPPED) {
        delete next[field];
      } else {
        next[field] = header;
      }
      return next;
    });
  }

  function handleSelectSaved(mappingId: string) {
    setSelectedSavedId(mappingId);
    if (!mappingId) {
      onMappingChange(null);
      return;
    }
    const mapping = savedMappings.find((m) => m.id === mappingId);
    if (mapping) {
      // Reflect the saved mapping's columns in the table for transparency,
      // then hand its id straight to the caller -- no re-save needed.
      setFieldMap(mapping.column_map);
      onMappingChange(mapping.id);
    }
  }

  async function handleSaveMapping() {
    setError(null);
    setSaving(true);
    try {
      const created = await createMapping({
        source_name: sourceName.trim(),
        target_kind: targetKind,
        column_map: fieldMap,
      });
      setSavedMappings((prev) => [...prev, created].sort((a, b) => a.source_name.localeCompare(b.source_name)));
      setSelectedSavedId(created.id);
      onMappingChange(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save this mapping.");
    } finally {
      setSaving(false);
    }
  }

  const usingSaved = Boolean(selectedSavedId);

  return (
    <div className="flex flex-col gap-6">
      <Card className="flex flex-col gap-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Preview</h3>
          <p className="text-sm text-text-muted">
            First {sampleRows.length} row{sampleRows.length === 1 ? "" : "s"} detected in the file.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-max text-left text-sm">
            <thead className="border-b border-border text-xs font-medium uppercase tracking-wide text-text-muted">
              <tr>
                {headers.map((header) => (
                  <th key={header} className="whitespace-nowrap p-3">
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sampleRows.map((row, idx) => (
                <tr key={idx} className="border-b border-border last:border-b-0">
                  {row.map((cell, cellIdx) => (
                    <td key={cellIdx} className="whitespace-nowrap p-3 text-text-muted">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {!loadingSaved && savedMappings.length > 0 && (
        <Card className="flex flex-col gap-3">
          <h3 className="text-lg font-semibold tracking-tight">Use a saved mapping</h3>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-text-muted">Saved mappings for this file type</span>
            <select
              className="h-11 rounded-sm border border-border bg-surface px-3 text-sm"
              value={selectedSavedId}
              onChange={(e) => handleSelectSaved(e.target.value)}
            >
              <option value="">Map columns manually instead</option>
              {savedMappings.map((mapping) => (
                <option key={mapping.id} value={mapping.id}>
                  {mapping.source_name}
                </option>
              ))}
            </select>
          </label>
          {usingSaved && <Badge variant="success">Using saved mapping - ready to submit</Badge>}
        </Card>
      )}

      {!usingSaved && (
        <Card className="flex flex-col gap-4">
          <h3 className="text-lg font-semibold tracking-tight">Map columns</h3>
          <div className="flex flex-col gap-3">
            {canonicalFields.map(({ field, label, required }) => (
              <label key={field} className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[1fr_2fr]">
                <span className="text-sm font-medium">
                  {label}
                  {required && <span className="text-danger"> *</span>}
                </span>
                <select
                  className="h-11 rounded-sm border border-border bg-surface px-3 text-sm"
                  value={fieldMap[field] ?? UNMAPPED}
                  onChange={(e) => handleFieldChange(field, e.target.value)}
                >
                  <option value={UNMAPPED}>{required ? "Select a column..." : "(skip)"}</option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>

          <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:items-end sm:justify-between">
            <label className="flex flex-col gap-1 text-sm sm:max-w-xs sm:flex-1">
              <span className="text-text-muted">Save this mapping as</span>
              <input
                type="text"
                className="h-11 rounded-sm border border-border bg-surface px-3 text-sm"
                placeholder="e.g. Chase business checking"
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
              />
            </label>
            <Button
              type="button"
              onClick={handleSaveMapping}
              disabled={!canSaveNewMapping || saving}
            >
              {saving ? "Saving..." : "Save mapping"}
            </Button>
          </div>
          {requiredMissing.length > 0 && (
            <p className="text-xs text-text-muted">
              Map required fields ({requiredMissing.map((f) => f.label).join(", ")}) before saving.
            </p>
          )}
          {error && <p className="text-sm text-danger">{error}</p>}
        </Card>
      )}
    </div>
  );
}
