"use client";

import { useState } from "react";
import type { AuditReportData } from "../../lib/agent-runtime";
import { AuditReportView } from "./AuditReportView";

async function postAudit(domainUrl: string, brand: string): Promise<AuditReportData> {
  const res = await fetch("/api/audit", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ domainUrl, brand: brand || undefined })
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { error?: string }).error ?? "Audit failed");
  return data as AuditReportData;
}

export function AuditRunner({ defaultUrl }: { defaultUrl: string }) {
  const [url, setUrl] = useState(defaultUrl);
  const [brand, setBrand] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<AuditReportData | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await postAudit(url.trim(), brand.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Audit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={run}
        className="rounded border border-line bg-white p-5 print:hidden"
      >
        <div className="grid gap-3 sm:grid-cols-[2fr_1fr_auto] sm:items-end">
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-moss">Website URL</span>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="queryclear.com"
              required
              className="mt-1 w-full rounded border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-moss"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-moss">Brand (optional)</span>
            <input
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="auto-detected"
              className="mt-1 w-full rounded border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-moss"
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            aria-busy={busy}
            className="h-[38px] rounded bg-ink px-4 text-sm font-semibold text-paper transition hover:bg-ink/90 disabled:opacity-60"
          >
            {busy ? "Auditing…" : "Run audit"}
          </button>
        </div>
        <p className="mt-3 text-xs text-ink/50">
          Read-only. Crawls public pages and probes AI visibility — never writes to the site.
        </p>
      </form>

      {error ? (
        <div className="rounded border border-line bg-paper px-5 py-3 text-sm text-ink print:hidden">
          <span className="font-semibold text-moss">Error:</span> {error}
        </div>
      ) : null}

      {busy ? (
        <div className="flex items-center gap-3 rounded border border-line bg-white px-5 py-4 text-sm text-ink/70">
          <span className="h-2 w-2 animate-pulse rounded-full bg-moss" aria-hidden />
          Crawling, checking AI visibility, and drafting a sample fix…
        </div>
      ) : null}

      {report ? <AuditReportView report={report} /> : null}
    </div>
  );
}
