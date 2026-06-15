import { NextResponse } from "next/server";
import { getApiTenant, runtimeErrorResponse, unauthorized } from "../../../../lib/api-helpers";
import { publishDraft } from "../../../../lib/agent-runtime";

export async function POST(request: Request) {
  const tenant = await getApiTenant();
  if (!tenant) {
    return unauthorized();
  }

  const body = (await request.json()) as { draftId?: string };
  if (!body.draftId) {
    return NextResponse.json({ error: "draftId is required" }, { status: 400 });
  }

  try {
    const result = await publishDraft(body.draftId, tenant.user.email);
    return NextResponse.json(result);
  } catch (error) {
    return runtimeErrorResponse(error);
  }
}
