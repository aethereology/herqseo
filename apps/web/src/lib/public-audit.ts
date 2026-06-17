/**
 * Abuse + cost guardrails for the PUBLIC lead-magnet audit.
 *
 * A public endpoint that calls OpenAI per request is a money bomb, so every
 * request must pass two gates before any model call:
 *   1. per-IP rate limit (stop a single abuser hammering the tool)
 *   2. a global daily spend cap (stop the whole tool exceeding the budget)
 *
 * Each audit's full report is cached briefly so the email gate can reveal it
 * without re-running (and re-paying for) the audit.
 *
 * The stores are behind interfaces. The in-memory impls here are correct for a
 * single long-lived process (local dev): Node is single-threaded so the
 * check-and-increment is atomic. In production on Vercel (many ephemeral
 * function instances) these MUST be backed by a shared store (Upstash Redis) or
 * the guards do nothing — see redis impl wired at deploy time.
 */
import type { AuditReportData } from "./agent-runtime";

const DAY_MS = 24 * 60 * 60 * 1000;

export interface RateLimitResult {
  allowed: boolean;
  retryAfterMs: number;
}

export interface SpendResult {
  allowed: boolean;
  spentUsd: number;
  capUsd: number;
}

export interface PublicAuditStore {
  /** Count one hit for an IP; deny once it exceeds the window limit. */
  rateLimit(ip: string, limit: number, windowMs: number): RateLimitResult;
  /** Reserve the estimated cost against today's cap; deny if it would exceed it. */
  reserveSpend(costUsd: number, capUsd: number): SpendResult;
  /** Release a reservation when the audit fails, so a failure doesn't burn budget. */
  releaseSpend(costUsd: number): void;
  putReport(token: string, report: AuditReportData, ttlMs: number): void;
  getReport(token: string): AuditReportData | null;
}

export interface Lead {
  email: string;
  domainUrl: string;
  source: "report-unlock" | "capacity-gate";
  createdAt: string;
}

export interface LeadSink {
  save(lead: Lead): Promise<void> | void;
}

interface Window {
  count: number;
  resetAt: number;
}

interface CachedReport {
  report: AuditReportData;
  expiresAt: number;
}

/** In-memory stores — local dev only (see file header). */
export class InMemoryPublicAuditStore implements PublicAuditStore {
  private readonly ipWindows = new Map<string, Window>();
  private spend = { day: "", usd: 0 };
  private readonly reports = new Map<string, CachedReport>();

  constructor(private readonly now: () => number = Date.now) {}

  rateLimit(ip: string, limit: number, windowMs: number): RateLimitResult {
    const t = this.now();
    const w = this.ipWindows.get(ip);
    if (!w || t >= w.resetAt) {
      this.ipWindows.set(ip, { count: 1, resetAt: t + windowMs });
      return { allowed: true, retryAfterMs: 0 };
    }
    if (w.count >= limit) {
      return { allowed: false, retryAfterMs: w.resetAt - t };
    }
    w.count += 1;
    return { allowed: true, retryAfterMs: 0 };
  }

  reserveSpend(costUsd: number, capUsd: number): SpendResult {
    const day = new Date(this.now()).toISOString().slice(0, 10);
    if (this.spend.day !== day) {
      this.spend = { day, usd: 0 };
    }
    if (this.spend.usd + costUsd > capUsd) {
      return { allowed: false, spentUsd: this.spend.usd, capUsd };
    }
    this.spend.usd += costUsd;
    return { allowed: true, spentUsd: this.spend.usd, capUsd };
  }

  releaseSpend(costUsd: number): void {
    this.spend.usd = Math.max(0, this.spend.usd - costUsd);
  }

  putReport(token: string, report: AuditReportData, ttlMs: number): void {
    this.reports.set(token, { report, expiresAt: this.now() + ttlMs });
  }

  getReport(token: string): AuditReportData | null {
    const hit = this.reports.get(token);
    if (!hit || this.now() >= hit.expiresAt) {
      this.reports.delete(token);
      return null;
    }
    return hit.report;
  }
}

/** In-memory lead sink — local dev only; wire to email/CRM/DB at deploy. */
export class InMemoryLeadSink implements LeadSink {
  readonly leads: Lead[] = [];
  save(lead: Lead): void {
    this.leads.push(lead);
  }
}

export interface PublicAuditConfig {
  dailyCapUsd: number;
  costPerAuditUsd: number;
  ipLimit: number;
  ipWindowMs: number;
  reportTtlMs: number;
}

export function publicAuditConfig(): PublicAuditConfig {
  const num = (v: string | undefined, fallback: number) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : fallback;
  };
  return {
    dailyCapUsd: num(process.env.PUBLIC_AUDIT_DAILY_CAP_USD, 5),
    // Conservative per-audit estimate (real ~$0.005); reserved before running.
    costPerAuditUsd: num(process.env.PUBLIC_AUDIT_COST_USD, 0.01),
    ipLimit: num(process.env.PUBLIC_AUDIT_IP_LIMIT, 5),
    ipWindowMs: num(process.env.PUBLIC_AUDIT_IP_WINDOW_MS, 60 * 60 * 1000),
    reportTtlMs: num(process.env.PUBLIC_AUDIT_REPORT_TTL_MS, DAY_MS)
  };
}

/** The summary a visitor sees for free, before the email gate. */
export interface AuditSummary {
  token: string;
  domainUrl: string;
  pageTitle: string;
  technicalIssues: number;
  invisibleQueries: number;
  recommendations: number;
  topFindings: { title: string; severity: string }[];
}

export function summarize(token: string, report: AuditReportData): AuditSummary {
  return {
    token,
    domainUrl: report.domain_url,
    pageTitle: report.page_title,
    technicalIssues: report.findings.length,
    invisibleQueries: report.queries.filter((q) => q.cited_count === 0).length,
    recommendations: report.recommendations.length,
    topFindings: report.findings.slice(0, 3).map((f) => ({ title: f.title, severity: f.severity }))
  };
}

// Process-wide singletons for local dev. Pinned to globalThis so they're shared
// across route modules (Next isolates module-level state per route otherwise).
// In production on Vercel each function instance has its own globalThis, so these
// MUST be replaced by Redis/email-backed impls at deploy time (see PROGRESS.md).
const globals = globalThis as typeof globalThis & {
  __qcPublicAuditStore?: PublicAuditStore;
  __qcLeadSink?: LeadSink;
};

export function publicAuditStore(): PublicAuditStore {
  return (globals.__qcPublicAuditStore ??= new InMemoryPublicAuditStore());
}

export function leadSink(): LeadSink {
  return (globals.__qcLeadSink ??= new InMemoryLeadSink());
}
