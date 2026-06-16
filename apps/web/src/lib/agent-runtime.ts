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

export interface WordPressPreflightResponse {
  ok: boolean;
  message: string;
}

export interface WordPressConnectResponse {
  ok: boolean;
  credentials_ref: string;
  base_url: string;
  username: string;
  message: string;
}

export interface WordPressStatusResponse {
  connected: boolean;
  base_url?: string;
  username?: string;
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
  engine: string;
  query: string;
  cited_count: number;
  samples: number;
  citation_frequency: number;
  confidence_low: number;
  confidence_high: number;
  // True only for a real, compliant query to the engine itself. False = a model
  // standing in for the engine (an estimate, not a live measurement).
  measured: boolean;
}

export interface AuditRecommendation {
  rank: number;
  priority: number;
  kind: string;
  title: string;
  rationale: string;
  action: string;
  provenance: string; // "measured" | "estimated"
  evidence: string;
}

export interface AuditReportData {
  domain_url: string;
  page_title: string;
  findings: AuditFinding[];
  queries: AuditQuery[];
  opportunities: RuntimeOpportunity[];
  recommendations: AuditRecommendation[];
  sample_draft: RuntimeDraft | null;
  detected_voice: string | null;
}

export interface AuditLogEntry {
  entity_id: string;
  action: string;
  actor: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
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
    const detail = await response
      .clone()
      .json()
      .then((body: { error?: string; detail?: string }) => body.error ?? body.detail ?? "")
      .catch(async () => response.text().catch(() => ""));
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

export function fetchAuditLog(orgId: string): Promise<AuditLogEntry[]> {
  return call<AuditLogEntry[]>(`/audit-log?org_id=${encodeURIComponent(orgId)}`, {
    method: "GET"
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

export function preflightWordPress(input: {
  baseUrl: string;
  username: string;
  appPassword: string;
}): Promise<WordPressPreflightResponse> {
  return call<WordPressPreflightResponse>("/integrations/wordpress/preflight", {
    method: "POST",
    body: JSON.stringify({
      base_url: input.baseUrl,
      username: input.username,
      app_password: input.appPassword
    })
  });
}

export function connectWordPress(input: {
  orgId: string;
  domainId: string;
  baseUrl: string;
  username: string;
  appPassword: string;
}): Promise<WordPressConnectResponse> {
  return call<WordPressConnectResponse>("/integrations/wordpress/connect", {
    method: "POST",
    body: JSON.stringify({
      org_id: input.orgId,
      domain_id: input.domainId,
      base_url: input.baseUrl,
      username: input.username,
      app_password: input.appPassword
    })
  });
}

export function getWordPressStatus(input: {
  orgId: string;
  domainId: string;
}): Promise<WordPressStatusResponse> {
  const params = new URLSearchParams({
    org_id: input.orgId,
    domain_id: input.domainId
  });
  return call<WordPressStatusResponse>(`/integrations/wordpress/status?${params}`, {
    method: "GET"
  });
}
