import { NextResponse } from "next/server";
import type { AuthenticatedTenant } from "@queryclear/shared";
import { auth } from "../../auth";
import { AgentRuntimeError } from "./agent-runtime";

export async function getApiTenant(): Promise<AuthenticatedTenant | null> {
  const session = await auth();
  return session?.tenant ?? null;
}

export function unauthorized(): NextResponse {
  return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
}

export function runtimeErrorResponse(error: unknown): NextResponse {
  if (error instanceof AgentRuntimeError) {
    return NextResponse.json({ error: error.message }, { status: error.status });
  }
  throw error;
}
