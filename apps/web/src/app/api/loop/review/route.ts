import { NextResponse } from "next/server";
import { getApiTenant, runtimeErrorResponse, unauthorized } from "../../../../lib/api-helpers";
import { reviewDraft } from "../../../../lib/agent-runtime";

export async function POST(request: Request) {
  const tenant = await getApiTenant();
  if (!tenant) {
    return unauthorized();
  }

  const body = (await request.json()) as {
    draftId?: string;
    approved?: boolean;
    note?: string;
  };
  if (!body.draftId || typeof body.approved !== "boolean") {
    return NextResponse.json({ error: "draftId and approved are required" }, { status: 400 });
  }

  try {
    const draft = await reviewDraft(body.draftId, {
      approved: body.approved,
      reviewer: tenant.user.email,
      note: body.note ?? null
    });
    return NextResponse.json(draft);
  } catch (error) {
    return runtimeErrorResponse(error);
  }
}
