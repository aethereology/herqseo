// Server-side client for the Python agent runtime (FastAPI adapter, D11).
// The browser never calls the runtime directly — only authenticated Next.js
// route handlers do, injecting tenant context.

const BASE_URL = process.env.AGENT_RUNTIME_URL ?? "http://localhost:8080";

export interface RuntimeOpportunity {
  id: string;
  type: string;
  title: string;
  rationale: string;
  priority: number;
  status: string;
}

export interface RuntimeDraft {
  id: string;
  opportunity_id: string;
  title: string;
  body: string;
  status: string;
  reviewer: string | null;
  cms_post_id: string | null;
  published_at: string | null;
  cost_usd: string;
}

export interface RunResponse {
  run_id: string;
  opportunities: RuntimeOpportunity[];
  draft: RuntimeDraft | null;
}

export interface PublishResponse {
  piece: RuntimeDraft;
  cms_post_id: string;
  url: string;
  status: string;
}

export interface AuditFinding {
  code: string;
  severity: string;
  title: string;
  detail: string;
  recommendation: string;
  url: string | null;
}

export interface AuditQuery {
  query: string;
  cited_count: number;
  samples: number;
  citation_frequency: number;
}

export interface AuditReportData {
  domain_url: string;
  page_title: string;
  findings: AuditFinding[];
  queries: AuditQuery[];
  opportunities: RuntimeOpportunity[];
  sample_draft: RuntimeDraft | null;
}

export class AgentRuntimeError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = "AgentRuntimeError";
  }
}

async function call<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init.headers },
      cache: "no-store"
    });
  } catch {
    throw new AgentRuntimeError(
      `Agent runtime unreachable at ${BASE_URL}. Start services/agent-runtime.`,
      503
    );
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new AgentRuntimeError(detail || response.statusText, response.status);
  }

  return (await response.json()) as T;
}

export function runLoop(input: {
  orgId: string;
  domainId: string;
  domainUrl: string;
  brand: string;
  brandVoice?: string;
  samples?: number;
}): Promise<RunResponse> {
  return call<RunResponse>("/runs", {
    method: "POST",
    body: JSON.stringify({
      org_id: input.orgId,
      domain_id: input.domainId,
      domain_url: input.domainUrl,
      brand: input.brand,
      brand_voice: input.brandVoice,
      samples: input.samples ?? 3
    })
  });
}

export function reviewDraft(
  draftId: string,
  input: { orgId: string; approved: boolean; reviewer: string; note?: string | null }
): Promise<RuntimeDraft> {
  return call<RuntimeDraft>(`/drafts/${encodeURIComponent(draftId)}/review`, {
    method: "POST",
    body: JSON.stringify({
      org_id: input.orgId,
      approved: input.approved,
      reviewer: input.reviewer,
      note: input.note ?? null
    })
  });
}

export function runAudit(input: {
  orgId: string;
  domainId: string;
  domainUrl: string;
  brand?: string;
  samples?: number;
}): Promise<AuditReportData> {
  // No brand voice: an audit derives the prospect's voice from their own site.
  return call<AuditReportData>("/audit", {
    method: "POST",
    body: JSON.stringify({
      org_id: input.orgId,
      domain_id: input.domainId,
      domain_url: input.domainUrl,
      brand: input.brand,
      samples: input.samples ?? 3
    })
  });
}

export function publishDraft(
  draftId: string,
  input: { orgId: string; actor: string }
): Promise<PublishResponse> {
  return call<PublishResponse>(`/drafts/${encodeURIComponent(draftId)}/publish`, {
    method: "POST",
    body: JSON.stringify({ org_id: input.orgId, actor: input.actor })
  });
}
