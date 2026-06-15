import { NextResponse } from "next/server";
import { getApiTenant, runtimeErrorResponse, unauthorized } from "../../../lib/api-helpers";
import { runAudit } from "../../../lib/agent-runtime";

export async function POST(request: Request) {
  const tenant = await getApiTenant();
  if (!tenant) {
    return unauthorized();
  }

  const body = (await request.json()) as { domainUrl?: string; brand?: string };
  const raw = (body.domainUrl ?? "").trim();
  if (!raw) {
    return NextResponse.json({ error: "domainUrl is required" }, { status: 400 });
  }
  const domainUrl = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;

  try {
    const report = await runAudit({
      orgId: tenant.organization.id,
      domainId: tenant.activeDomain.id,
      domainUrl,
      brand: body.brand?.trim() || undefined,
      brandVoice: tenant.activeDomain.brandVoice
    });
    return NextResponse.json(report);
  } catch (error) {
    return runtimeErrorResponse(error);
  }
}
