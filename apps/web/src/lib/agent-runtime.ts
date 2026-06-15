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
  samples?: number;
}): Promise<RunResponse> {
  return call<RunResponse>("/runs", {
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

export function reviewDraft(
  draftId: string,
  input: { approved: boolean; reviewer: string; note?: string | null }
): Promise<RuntimeDraft> {
  return call<RuntimeDraft>(`/drafts/${encodeURIComponent(draftId)}/review`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function publishDraft(draftId: string, actor: string): Promise<PublishResponse> {
  return call<PublishResponse>(`/drafts/${encodeURIComponent(draftId)}/publish`, {
    method: "POST",
    body: JSON.stringify({ actor })
  });
}
