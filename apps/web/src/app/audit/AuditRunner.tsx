"use client";

import { useState } from "react";
import type {
  AuditFinding,
  AuditQuery,
  AuditRecommendation,
  AuditReportData,
  RuntimeDraft
} from "../../lib/agent-runtime";

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

const SEVERITY: Record<string, string> = {
  high: "border-ink/30 bg-ink text-paper",
  medium: "border-moss/40 bg-moss/10 text-moss",
  low: "border-line bg-paper text-ink/60"
};

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

      {report ? <Report report={report} /> : null}
    </div>
  );
}

function Report({ report }: { report: AuditReportData }) {
  const gaps = report.queries.filter((q) => q.cited_count === 0).length;
  return (
    <article className="space-y-6" aria-live="polite">
      <header className="flex flex-col justify-between gap-3 rounded border border-line bg-ink p-5 text-paper sm:flex-row sm:items-center">
        <div>
          <p className="text-xs uppercase tracking-wide text-lime">AI Search Audit</p>
          <h2 className="mt-1 text-xl font-semibold">{report.domain_url}</h2>
          <p className="mt-1 text-sm text-paper/70">{report.page_title || "(no page title found)"}</p>
        </div>
        <div className="flex gap-5 text-center">
          <Stat n={report.findings.length} label="Technical issues" />
          <Stat n={gaps} label="Invisible queries" />
          <button
            onClick={() => window.print()}
            className="self-center rounded border border-paper/30 px-3 py-2 text-xs font-semibold text-paper transition hover:bg-paper/10 print:hidden"
          >
            Print / PDF
          </button>
        </div>
      </header>

      {report.detected_voice ? (
        <Section title="Detected brand voice">
          <p className="px-5 py-4 text-sm italic leading-6 text-ink/70">
            “{report.detected_voice}”
          </p>
          <p className="px-5 pb-4 text-xs text-ink/50">
            Inferred from your own site copy — the sample draft below is written in this voice.
          </p>
        </Section>
      ) : null}

      {report.recommendations.length > 0 ? (
        <Section title={`Prioritized recommendations (${report.recommendations.length})`}>
          <ol className="divide-y divide-line">
            {report.recommendations.map((r) => (
              <RecRow key={r.rank} r={r} />
            ))}
          </ol>
        </Section>
      ) : null}

      <Section title={`Technical findings (${report.findings.length})`}>
        {report.findings.length === 0 ? (
          <p className="px-5 py-4 text-sm text-ink/60">No on-page issues found in the checks we run.</p>
        ) : (
          <ul className="divide-y divide-line">
            {report.findings.map((f, i) => (
              <FindingRow key={`${f.code}-${i}`} f={f} />
            ))}
          </ul>
        )}
      </Section>

      <Section title={`AI visibility (${report.queries.length} queries tested)`}>
        {report.queries.some((q) => !q.measured) ? (
          <p className="border-b border-line bg-paper/60 px-5 py-3 text-xs leading-5 text-ink/60">
            Results marked <EstBadge /> are modeled estimates: a language model
            answering as that engine would, sampled repeatedly — not a live query
            to the engine itself. They show where you&apos;re likely invisible, not a
            measured citation rate. Direct, compliant per-engine measurement rolls
            out as each engine&apos;s API is connected.
          </p>
        ) : null}
        <ul className="divide-y divide-line">
          {report.queries.map((q) => (
            <QueryRow key={`${q.engine}-${q.query}`} q={q} />
          ))}
        </ul>
      </Section>

      {report.sample_draft ? (
        <Section title="Sample fix — ready-to-review draft">
          <div className="px-5 py-4">
            <h4 className="text-sm font-semibold text-ink">{report.sample_draft.title}</h4>
            <Draft draft={report.sample_draft} />
          </div>
        </Section>
      ) : null}
    </article>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div>
      <div className="text-2xl font-semibold text-lime">{n}</div>
      <div className="text-xs text-paper/70">{label}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded border border-line bg-white">
      <div className="border-b border-line px-5 py-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-moss">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function RecRow({ r }: { r: AuditRecommendation }) {
  const estimated = r.provenance === "estimated";
  return (
    <li className="flex gap-3 px-5 py-4">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink text-xs font-semibold text-paper">
        {r.rank}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-semibold text-ink">{r.title}</h4>
          <span className="rounded border border-line bg-paper px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink/55">
            {r.kind}
          </span>
          {estimated ? <EstBadge /> : null}
        </div>
        <p className="mt-1 text-sm text-ink/65">{r.rationale}</p>
        <p className="mt-1 text-sm text-ink/80">
          <span className="font-medium text-moss">Do:</span> {r.action}
        </p>
      </div>
    </li>
  );
}

function FindingRow({ f }: { f: AuditFinding }) {
  return (
    <li className="px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-ink">{f.title}</h4>
        <span
          className={`shrink-0 rounded border px-2 py-0.5 text-xs font-semibold uppercase ${SEVERITY[f.severity] ?? SEVERITY.low}`}
        >
          {f.severity}
        </span>
      </div>
      <p className="mt-1 text-sm text-ink/65">{f.detail}</p>
      <p className="mt-1 text-sm text-ink/80">
        <span className="font-medium text-moss">Fix:</span> {f.recommendation}
      </p>
    </li>
  );
}

function EstBadge() {
  return (
    <span
      className="inline-block rounded border border-line bg-paper px-1 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink/45"
      title="Modeled estimate — a language model answering as this engine would, not a live query to the engine."
    >
      est.
    </span>
  );
}

function QueryRow({ q }: { q: AuditQuery }) {
  const invisible = q.cited_count === 0;
  return (
    <li className="flex items-center justify-between gap-3 px-5 py-3">
      <span className="min-w-0 text-sm text-ink">
        <span className="mr-2 inline-flex items-center gap-1 rounded border border-line bg-paper px-1.5 py-0.5 text-[11px] font-semibold uppercase text-ink/55">
          {q.engine.replaceAll("_", " ")}
          {!q.measured ? <EstBadge /> : null}
        </span>
        {q.query}
      </span>
      <span
        className={`shrink-0 rounded border px-2 py-0.5 text-xs font-semibold ${
          invisible ? "border-ink/30 bg-ink text-paper" : "border-moss/40 bg-moss/10 text-moss"
        }`}
        title={`95% confidence: ${(q.confidence_low * 100).toFixed(0)}%-${(q.confidence_high * 100).toFixed(0)}%`}
      >
        {invisible ? "not cited" : `cited ${q.cited_count}/${q.samples}`}
      </span>
    </li>
  );
}

function Draft({ draft }: { draft: RuntimeDraft }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs font-semibold text-moss underline print:hidden"
      >
        {open ? "Hide draft" : "Show draft"}
      </button>
      {open ? (
        <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded border border-line bg-paper/60 px-4 py-3 font-mono text-sm leading-6 text-ink/80">
          {draft.body}
        </pre>
      ) : null}
    </div>
  );
}
