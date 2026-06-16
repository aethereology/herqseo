import { NextResponse } from "next/server";
import { getApiTenant, runtimeErrorResponse, unauthorized } from "../../../../../lib/api-helpers";
import { getWordPressStatus } from "../../../../../lib/agent-runtime";

export async function GET() {
  const tenant = await getApiTenant();
  if (!tenant) {
    return unauthorized();
  }

  try {
    const result = await getWordPressStatus({
      orgId: tenant.organization.id,
      domainId: tenant.activeDomain.id
    });
    return NextResponse.json(result);
  } catch (error) {
    return runtimeErrorResponse(error);
  }
}
