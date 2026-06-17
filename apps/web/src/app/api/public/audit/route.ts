import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import { runAudit, AgentRuntimeError } from "../../../../lib/agent-runtime";
import {
  publicAuditConfig,
  publicAuditStore,
  summarize
} from "../../../../lib/public-audit";

export const dynamic = "force-dynamic";

// Public org/domain the runtime meters audits against (a second, per-audit cost
// bound beneath the web layer's daily cap). Defaults to the dev tenant locally.
const ORG_ID = process.env.PUBLIC_AUDIT_ORG_ID ?? "org_dev_queryclear";
const DOMAIN_ID = process.env.PUBLIC_AUDIT_DOMAIN_ID ?? "domain_dev_queryclear";

function clientIp(request: Request): string {
  const fwd = request.headers.get("x-forwarded-for");
  return fwd?.split(",")[0]?.trim() || request.headers.get("x-real-ip") || "unknown";
}

export async function POST(request: Request) {
  const cfg = publicAuditConfig();
  const store = publicAuditStore();

  const body = (await request.json().catch(() => ({}))) as { domainUrl?: string };
  const raw = (body.domainUrl ?? "").trim();
  if (!raw) {
    return NextResponse.json({ error: "domainUrl is required" }, { status: 400 });
  }
  const domainUrl = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;

  // Gate 1 — per-IP rate limit (abuse).
  const rl = store.rateLimit(clientIp(request), cfg.ipLimit, cfg.ipWindowMs);
  if (!rl.allowed) {
    return NextResponse.json(
      { error: "Too many audits from your network. Try again later." },
      { status: 429, headers: { "retry-after": String(Math.ceil(rl.retryAfterMs / 1000)) } }
    );
  }

  // Gate 2 — global daily spend cap. When hit, we don't call OpenAI; we offer to
  // email the report (a lead), so a real visitor isn't lost.
  const spend = store.reserveSpend(cfg.costPerAuditUsd, cfg.dailyCapUsd);
  if (!spend.allowed) {
    return NextResponse.json({ gated: true, domainUrl });
  }

  try {
    const report = await runAudit({ orgId: ORG_ID, domainId: DOMAIN_ID, domainUrl });
    const token = randomUUID();
    store.putReport(token, report, cfg.reportTtlMs);
    return NextResponse.json({ summary: summarize(token, report) });
  } catch (error) {
    store.releaseSpend(cfg.costPerAuditUsd); // failed audit shouldn't burn budget
    if (error instanceof AgentRuntimeError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    throw error;
  }
}
