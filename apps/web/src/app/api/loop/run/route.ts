import { NextResponse } from "next/server";
import { getApiTenant, runtimeErrorResponse, unauthorized } from "../../../../lib/api-helpers";
import { runLoop } from "../../../../lib/agent-runtime";

export async function POST() {
  const tenant = await getApiTenant();
  if (!tenant) {
    return unauthorized();
  }

  try {
    const result = await runLoop({
      orgId: tenant.organization.id,
      domainId: tenant.activeDomain.id,
      domainUrl: tenant.activeDomain.url,
      brand: tenant.organization.name
    });
    return NextResponse.json(result);
  } catch (error) {
    return runtimeErrorResponse(error);
  }
}
