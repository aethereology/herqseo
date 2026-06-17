"use client";

import { useState } from "react";
import type { AuditReportData } from "../../lib/agent-runtime";
import { AuditReportView, Section } from "../audit/AuditReportView";

interface AuditSummary {
  token: string;
  domainUrl: string;
  pageTitle: string;
  technicalIssues: number;
  invisibleQueries: number;
  recommendations: number;
  topFindings: { title: string; severity: string }[];
}

type Phase = "input" | "summary" | "gated" | "full";

export function FreeAudit() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("input");
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [gatedDomain, setGatedDomain] = useState("");
  const [fullReport, setFullReport] = useState<AuditReportData | null>(null);

  async function runAudit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSummary(null);
    try {
      const res = await fetch("/api/public/audit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ domainUrl: url.trim() })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error((data as { error?: string }).error ?? "Audit failed");
      if ((data as { gated?: boolean }).gated) {
        setGatedDomain((data as { domainUrl: string }).domainUrl);
        setPhase("gated");
      } else {
        setSummary((data as { summary: AuditSummary }).summary);
        setPhase("summary");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Audit failed");
    } finally {
      setBusy(false);
    }
  }

  if (phase === "full" && fullReport) {
    return <AuditReportView report={fullReport} />;
  }

  return (
    <div className="space-y-6">
      <form onSubmit={runAudit} className="rounded border border-line bg-white p-5">
        <label className="block">
          <span className="text-xs font-medium uppercase tracking-wide text-moss">
            Your website
          </span>
          <div className="mt-1 flex flex-col gap-2 sm:flex-row">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="yourcompany.com"
              required
              disabled={busy}
              className="w-full rounded border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-moss"
            />
            <button
              type="submit"
              disabled={busy}
              aria-busy={busy}
              className="shrink-0 rounded bg-ink px-5 py-2 text-sm font-semibold text-paper transition hover:bg-ink/90 disabled:opacity-60"
            >
              {busy ? "Auditing…" : "Run free audit"}
            </button>
          </div>
        </label>
        <p className="mt-3 text-xs text-ink/50">
          Read-only. We crawl public pages and probe AI visibility — we never write to your site.
        </p>
      </form>

      {error ? (
        <div className="rounded border border-line bg-paper px-5 py-3 text-sm text-ink">
          <span className="font-semibold text-moss">Error:</span> {error}
        </div>
      ) : null}

      {busy ? (
        <div className="flex items-center gap-3 rounded border border-line bg-white px-5 py-4 text-sm text-ink/70">
          <span className="h-2 w-2 animate-pulse rounded-full bg-moss" aria-hidden />
          Crawling, checking AI visibility, and drafting a sample fix… (~20s)
        </div>
      ) : null}

      {phase === "summary" && summary ? (
        <SummaryCard
          summary={summary}
          onUnlock={(report) => {
            setFullReport(report);
            setPhase("full");
          }}
        />
      ) : null}

      {phase === "gated" ? <CapacityGate domainUrl={gatedDomain} /> : null}
    </div>
  );
}

function SummaryCard({
  summary,
  onUnlock
}: {
  summary: AuditSummary;
  onUnlock: (report: AuditReportData) => void;
}) {
  return (
    <article className="space-y-6">
      <header className="rounded border border-line bg-ink p-5 text-paper">
        <p className="text-xs uppercase tracking-wide text-lime">Free preview</p>
        <h2 className="mt-1 text-xl font-semibold">{summary.domainUrl}</h2>
        <div className="mt-4 flex gap-6">
          <Stat n={summary.technicalIssues} label="Technical issues" />
          <Stat n={summary.invisibleQueries} label="Invisible queries" />
          <Stat n={summary.recommendations} label="Recommendations" />
        </div>
      </header>

      {summary.topFindings.length > 0 ? (
        <Section title="A few of the issues we found">
          <ul className="divide-y divide-line">
            {summary.topFindings.map((f, i) => (
              <li key={i} className="flex items-center justify-between gap-3 px-5 py-3">
                <span className="text-sm text-ink">{f.title}</span>
                <span className="shrink-0 rounded border border-line bg-paper px-2 py-0.5 text-xs font-semibold uppercase text-ink/55">
                  {f.severity}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <UnlockForm token={summary.token} domainUrl={summary.domainUrl} onUnlock={onUnlock} />
    </article>
  );
}

function UnlockForm({
  token,
  domainUrl,
  onUnlock
}: {
  token: string;
  domainUrl: string;
  onUnlock: (report: AuditReportData) => void;
}) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/public/lead", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim(), token, domainUrl })
      });
      const data = (await res.json().catch(() => ({}))) as {
        error?: string;
        report?: AuditReportData;
      };
      if (!res.ok) throw new Error(data.error ?? "Something went wrong");
      if (data.report) onUnlock(data.report);
      else throw new Error("This report has expired. Please run the audit again.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded border border-moss/40 bg-moss/5 p-5">
      <h3 className="text-sm font-semibold text-ink">
        Get the full report — prioritized fixes + a sample draft in your brand voice
      </h3>
      <p className="mt-1 text-sm text-ink/65">
        Enter your email and we&apos;ll unlock the complete audit instantly.
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          required
          disabled={busy}
          className="w-full rounded border border-line bg-white px-3 py-2 text-sm text-ink outline-none focus:border-moss"
        />
        <button
          type="submit"
          disabled={busy}
          className="shrink-0 rounded bg-ink px-5 py-2 text-sm font-semibold text-paper transition hover:bg-ink/90 disabled:opacity-60"
        >
          {busy ? "Unlocking…" : "Show full report"}
        </button>
      </div>
      {error ? <p className="mt-2 text-sm text-ink/70">{error}</p> : null}
    </form>
  );
}

function CapacityGate({ domainUrl }: { domainUrl: string }) {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/public/lead", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim(), domainUrl })
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) throw new Error(data.error ?? "Something went wrong");
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="rounded border border-moss/40 bg-moss/5 px-5 py-4 text-sm text-ink">
        Thanks — we&apos;ll email your audit for {domainUrl} shortly.
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="rounded border border-moss/40 bg-moss/5 p-5">
      <h3 className="text-sm font-semibold text-ink">We&apos;re at capacity for today</h3>
      <p className="mt-1 text-sm text-ink/65">
        The free audit is in high demand. Leave your email and we&apos;ll send your full audit
        for {domainUrl} as soon as a slot opens.
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          required
          disabled={busy}
          className="w-full rounded border border-line bg-white px-3 py-2 text-sm text-ink outline-none focus:border-moss"
        />
        <button
          type="submit"
          disabled={busy}
          className="shrink-0 rounded bg-ink px-5 py-2 text-sm font-semibold text-paper transition hover:bg-ink/90 disabled:opacity-60"
        >
          {busy ? "Sending…" : "Email me the audit"}
        </button>
      </div>
      {error ? <p className="mt-2 text-sm text-ink/70">{error}</p> : null}
    </form>
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
