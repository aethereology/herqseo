"use client";

import { useState } from "react";
import type {
  PublishResponse,
  RunResponse,
  RuntimeDraft,
  RuntimeOpportunity
} from "../lib/agent-runtime";

type Phase = "idle" | "running" | "ready";

async function post<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error((data as { error?: string }).error ?? "Request failed");
  }
  return data as T;
}

const STATUS_STYLES: Record<string, string> = {
  pending_approval: "border-moss/40 bg-moss/10 text-moss",
  approved: "border-ink/30 bg-ink text-paper",
  rejected: "border-line bg-paper text-ink/60",
  published: "border-ink/20 bg-lime text-ink"
};

function StatusPill({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? "border-line bg-paper text-ink/70";
  return (
    <span
      className={`w-fit rounded border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${style}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function OperatorConsole({
  domainUrl,
  brand,
  autonomyModeLabel
}: {
  domainUrl: string;
  brand: string;
  autonomyModeLabel: string;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<RunResponse | null>(null);
  const [draft, setDraft] = useState<RuntimeDraft | null>(null);
  const [published, setPublished] = useState<PublishResponse | null>(null);

  async function handleRun() {
    setPhase("running");
    setError(null);
    setPublished(null);
    setDraft(null);
    try {
      const result = await post<RunResponse>("/api/loop/run");
      setRun(result);
      setDraft(result.draft);
      setPhase("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
      setPhase("idle");
    }
  }

  async function handleReview(approved: boolean) {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await post<RuntimeDraft>("/api/loop/review", {
        draftId: draft.id,
        approved
      });
      setDraft(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }

  async function handlePublish() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const result = await post<PublishResponse>("/api/loop/publish", { draftId: draft.id });
      setPublished(result);
      setDraft(result.piece);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Publish failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded border border-line bg-white">
      <div className="flex flex-col gap-4 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-ink">Operator Loop</h2>
          <p className="mt-1 text-sm text-ink/60">
            Crawl <span className="font-medium text-ink/80">{domainUrl}</span> · probe AI
            visibility for <span className="font-medium text-ink/80">{brand}</span> · draft one fix
          </p>
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={phase === "running"}
          aria-busy={phase === "running"}
          className="rounded bg-ink px-4 py-2 text-sm font-semibold text-paper transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {phase === "running" ? "Running loop…" : "Run operator loop"}
        </button>
      </div>

      {error ? (
        <div className="border-b border-line bg-paper px-5 py-3 text-sm text-ink">
          <span className="font-semibold text-moss">Error:</span> {error}
        </div>
      ) : null}

      <div className="px-5 py-5" aria-live="polite">
        {phase === "idle" && !error ? (
          <p className="text-sm leading-6 text-ink/60">
            Run the loop to crawl the site, sample AI engines for brand citation, surface
            opportunities, and generate one answer-first draft for review.
          </p>
        ) : null}

        {phase === "running" ? (
          <div className="flex items-center gap-3 text-sm text-ink/70">
            <span className="h-2 w-2 animate-pulse rounded-full bg-moss" aria-hidden />
            Crawling, sampling engines, and drafting — every model call is metered.
          </div>
        ) : null}

        {phase === "ready" && run ? (
          <div className="space-y-6">
            <div className="flex items-center justify-between text-xs uppercase tracking-wide text-moss">
              <span>Opportunities ({run.opportunities.length})</span>
              <span className="font-mono lowercase text-ink/40">{run.run_id}</span>
            </div>

            {run.opportunities.length === 0 ? (
              <p className="text-sm text-ink/60">
                No visibility gaps above threshold — the brand is already cited. Nothing to draft.
              </p>
            ) : (
              <ul className="space-y-3">
                {run.opportunities.map((opportunity) => (
                  <OpportunityRow key={opportunity.id} opportunity={opportunity} />
                ))}
              </ul>
            )}

            {draft ? (
              <article className="rounded border border-line bg-paper/60">
                <div className="flex flex-col gap-3 border-b border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <h3 className="text-base font-semibold text-ink">{draft.title}</h3>
                  <StatusPill status={draft.status} />
                </div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap px-4 py-4 font-mono text-sm leading-6 text-ink/80">
                  {draft.body}
                </pre>
                <div className="flex flex-col gap-3 border-t border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <span className="font-mono text-xs text-ink/50">cost ${draft.cost_usd}</span>
                  <DraftActions
                    draft={draft}
                    published={published}
                    busy={busy}
                    autonomyModeLabel={autonomyModeLabel}
                    onReview={handleReview}
                    onPublish={handlePublish}
                  />
                </div>
              </article>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function OpportunityRow({ opportunity }: { opportunity: RuntimeOpportunity }) {
  return (
    <li className="rounded border border-line bg-white px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-ink">{opportunity.title}</h4>
        <span className="shrink-0 rounded border border-line px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-moss">
          P{opportunity.priority} · {opportunity.type}
        </span>
      </div>
      <p className="mt-2 text-sm leading-6 text-ink/65">{opportunity.rationale}</p>
    </li>
  );
}

function DraftActions({
  draft,
  published,
  busy,
  autonomyModeLabel,
  onReview,
  onPublish
}: {
  draft: RuntimeDraft;
  published: PublishResponse | null;
  busy: boolean;
  autonomyModeLabel: string;
  onReview: (approved: boolean) => void;
  onPublish: () => void;
}) {
  if (published || draft.status === "published") {
    return (
      <div className="text-right text-sm">
        <span className="font-semibold text-ink">Published to staging draft</span>
        <span className="mt-1 block font-mono text-xs text-ink/50">
          post #{draft.cms_post_id}
          {published?.url ? (
            <>
              {" · "}
              <a className="underline" href={published.url} target="_blank" rel="noreferrer">
                view draft
              </a>
            </>
          ) : null}
        </span>
      </div>
    );
  }

  if (draft.status === "rejected") {
    return <span className="text-sm text-ink/55">Rejected — run the loop again for a new draft.</span>;
  }

  if (draft.status === "approved") {
    return (
      <div className="flex flex-col items-end gap-1">
        <button
          type="button"
          onClick={onPublish}
          disabled={busy}
          aria-busy={busy}
          className="rounded bg-lime px-4 py-2 text-sm font-semibold text-ink transition hover:brightness-95 disabled:opacity-60"
        >
          {busy ? "Publishing…" : "Publish to staging"}
        </button>
        <span className="text-xs text-ink/45">WordPress draft only — never live ({autonomyModeLabel} mode)</span>
      </div>
    );
  }

  // pending_approval
  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => onReview(false)}
        disabled={busy}
        className="rounded border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-paper disabled:opacity-60"
      >
        Reject
      </button>
      <button
        type="button"
        onClick={() => onReview(true)}
        disabled={busy}
        aria-busy={busy}
        className="rounded bg-ink px-4 py-2 text-sm font-semibold text-paper transition hover:bg-ink/90 disabled:opacity-60"
      >
        {busy ? "Saving…" : "Approve"}
      </button>
    </div>
  );
}
