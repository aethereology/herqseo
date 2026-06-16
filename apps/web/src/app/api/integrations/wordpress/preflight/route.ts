import { NextResponse } from "next/server";
import { getApiTenant, runtimeErrorResponse, unauthorized } from "../../../../../lib/api-helpers";
import { preflightWordPress } from "../../../../../lib/agent-runtime";

export async function POST(request: Request) {
  const tenant = await getApiTenant();
  if (!tenant) {
    return unauthorized();
  }

  const body = (await request.json()) as {
    baseUrl?: string;
    username?: string;
    appPassword?: string;
  };
  const baseUrl = body.baseUrl?.trim();
  const username = body.username?.trim();
  const appPassword = body.appPassword?.trim();
  if (!baseUrl || !username || !appPassword) {
    return NextResponse.json(
      { error: "baseUrl, username, and appPassword are required" },
      { status: 400 }
    );
  }

  try {
    const result = await preflightWordPress({ baseUrl, username, appPassword });
    return NextResponse.json(result);
  } catch (error) {
    return runtimeErrorResponse(error);
  }
}
