"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getStoredAuthHeader, storeAuthHeader } from "@/lib/backend-auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

type Status = "checking" | "ok" | "needs-login";

/**
 * Gates the whole app behind the backend's Basic Auth, when the backend has
 * it configured. A plain fetch() to a different origin doesn't trigger the
 * browser's native credential prompt the way a page navigation would, so
 * this is the frontend-side counterpart: it asks once, stores the header
 * for the tab session, and every request in lib/api-client.ts attaches it.
 *
 * When the backend has no Basic Auth configured (local development), the
 * probe request below succeeds without credentials and the gate never
 * appears -- it adapts to the backend rather than needing its own flag.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("checking");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function probe(headerOverride?: string): Promise<boolean> {
    const header = headerOverride ?? getStoredAuthHeader();
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/mappings`, {
        headers: header ? { Authorization: header } : undefined,
      });
      if (response.status === 401) return false;
      // Any other outcome (200, or a non-auth error like a 5xx/network
      // hiccup) shouldn't block the app behind a login screen for a
      // problem that has nothing to do with credentials.
      return true;
    } catch {
      return true;
    }
  }

  useEffect(() => {
    let cancelled = false;
    probe().then((ok) => {
      if (!cancelled) setStatus(ok ? "ok" : "needs-login");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const header = `Basic ${btoa(`${username}:${password}`)}`;
    const ok = await probe(header);
    setSubmitting(false);
    if (!ok) {
      setError("Incorrect username or password.");
      return;
    }
    storeAuthHeader(username, password);
    setStatus("ok");
  }

  if (status === "checking") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-text-muted">Loading…</p>
      </div>
    );
  }

  if (status === "needs-login") {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <Card className="w-full max-w-sm">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <h1 className="text-lg font-semibold text-text">Sign in</h1>
              <p className="text-sm text-text-muted">
                This deployment requires credentials.
              </p>
            </div>
            <label className="flex flex-col gap-1 text-sm text-text">
              Username
              <input
                className="rounded-sm border border-border bg-surface px-3 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-text/70"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoFocus
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-text">
              Password
              <input
                type="password"
                className="rounded-sm border border-border bg-surface px-3 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-text/70"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            {error && <p className="text-sm text-danger">{error}</p>}
            <Button type="submit" disabled={submitting}>
              {submitting ? "Checking…" : "Sign in"}
            </Button>
          </form>
        </Card>
      </div>
    );
  }

  return <>{children}</>;
}
