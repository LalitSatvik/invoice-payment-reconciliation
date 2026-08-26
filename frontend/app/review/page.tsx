"use client";

import { useEffect, useState } from "react";
import { ApiError, acceptMatch, getMatch, listMatches, rejectMatch, runMatching } from "@/lib/api-client";
import type { MatchDetailOut } from "@/lib/types";
import { confidenceBand, MatchRow } from "@/components/review/MatchRow";
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

type BandFilter = "all" | "auto" | "review";

const bandFilterLabel: Record<BandFilter, string> = {
  all: "All confidence bands",
  auto: "Auto-suggested (>=85)",
  review: "Needs review (60-85)",
};

/** Fetches every suggested match's full side-by-side detail. A plain data
 * function with no state access, so it can be reused from both the mount
 * effect and the imperative refresh below without either one having to
 * route through the other. */
function fetchSuggestedMatches(): Promise<{ details: MatchDetailOut[]; total: number }> {
  return listMatches({ status: "suggested", limit: 200 }).then((list) =>
    Promise.all(list.items.map((item) => getMatch(item.id))).then((details) => ({
      details,
      total: list.total,
    })),
  );
}

export default function ReviewPage() {
  const [matches, setMatches] = useState<MatchDetailOut[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bandFilter, setBandFilter] = useState<BandFilter>("all");
  const [running, setRunning] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  // Mount-only fetch. Every state update here happens inside a `.then`/
  // `.catch`/`.finally` callback rather than synchronously in the effect
  // body, so nothing here runs before the request settles.
  useEffect(() => {
    let cancelled = false;
    fetchSuggestedMatches()
      .then(({ details, total: newTotal }) => {
        if (cancelled) return;
        setMatches(details);
        setTotal(newTotal);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load matches.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function refresh() {
    setLoading(true);
    setError(null);
    fetchSuggestedMatches()
      .then(({ details, total: newTotal }) => {
        setMatches(details);
        setTotal(newTotal);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load matches.");
      })
      .finally(() => setLoading(false));
  }

  async function handleRunMatching() {
    setRunning(true);
    setRunMessage(null);
    setError(null);
    try {
      const result = await runMatching();
      setRunMessage(
        `Matching run complete: ${result.matches_created} match(es), ${result.exceptions_created} exception(s) created.`,
      );
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Matching run failed.");
    } finally {
      setRunning(false);
    }
  }

  async function handleAccept(matchId: string) {
    await acceptMatch(matchId);
    setMatches((prev) => prev.filter((m) => m.id !== matchId));
    setTotal((prev) => Math.max(0, prev - 1));
  }

  async function handleReject(matchId: string) {
    await rejectMatch(matchId);
    setMatches((prev) => prev.filter((m) => m.id !== matchId));
    setTotal((prev) => Math.max(0, prev - 1));
  }

  const visible = matches.filter(
    (m) => bandFilter === "all" || confidenceBand(Number(m.confidence_score)) === bandFilter,
  );

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-4">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Review</span>
        <h1 className="text-3xl font-extrabold tracking-tight">Match review</h1>
        <PillNav items={navItems} activeHref="/review" />
      </header>

      <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium">Matching engine</p>
          <p className="text-sm text-text-muted">
            Run matching against all currently-unmatched invoices and payments.
          </p>
        </div>
        <Button type="button" variant="secondary" disabled={running} onClick={handleRunMatching}>
          {running ? "Running..." : "Run matching"}
        </Button>
      </Card>

      {runMessage && (
        <Card className="border-success/30 bg-success-bg">
          <p className="text-sm text-success">{runMessage}</p>
        </Card>
      )}

      {error && (
        <Card className="border-danger/30 bg-danger-bg">
          <p className="text-sm text-danger">{error}</p>
        </Card>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-text-muted">Filter</span>
          <select
            value={bandFilter}
            onChange={(e) => setBandFilter(e.target.value as BandFilter)}
            className="h-9 rounded-sm border border-border bg-surface px-3 text-sm"
          >
            {(Object.keys(bandFilterLabel) as BandFilter[]).map((key) => (
              <option key={key} value={key}>
                {bandFilterLabel[key]}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-text-muted">
          {visible.length} shown{total > matches.length ? ` of ${total} total suggested` : ""}
        </span>
      </div>

      {loading && (
        <Card>
          <p className="text-sm text-text-muted">Loading suggested matches...</p>
        </Card>
      )}

      {!loading && visible.length === 0 && !error && (
        <Card>
          <p className="text-sm text-text-muted">
            No suggested matches to review. Run matching above once invoices and payments are uploaded.
          </p>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        {visible.map((match) => (
          <MatchRow key={match.id} match={match} onAccept={handleAccept} onReject={handleReject} />
        ))}
      </div>
    </div>
  );
}
