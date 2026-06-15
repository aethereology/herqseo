import { PLAN_LIMITS, type PlanTier } from "@queryclear/shared";

export const TENANT_HEADER = "x-queryclear-org-id";

export function createHealthPayload(plan: PlanTier = "operator") {
  return {
    ok: true,
    service: "queryclear-api",
    tenantHeader: TENANT_HEADER,
    planLimits: PLAN_LIMITS[plan]
  };
}
