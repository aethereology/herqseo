export const PLAN_TIERS = ["operator", "growth", "scale", "agency", "enterprise"] as const;
export type PlanTier = (typeof PLAN_TIERS)[number];

export const AUTONOMY_MODE_KEYS = ["review", "auto_publish", "autopilot"] as const;
export type AutonomyMode = (typeof AUTONOMY_MODE_KEYS)[number];

export const AUTONOMY_MODES: Record<
  AutonomyMode,
  { label: string; requiresApproval: boolean; livePublishAllowed: boolean }
> = {
  review: {
    label: "Review",
    requiresApproval: true,
    livePublishAllowed: false
  },
  auto_publish: {
    label: "Auto-publish",
    requiresApproval: false,
    livePublishAllowed: true
  },
  autopilot: {
    label: "Autopilot",
    requiresApproval: false,
    livePublishAllowed: true
  }
};

export const AI_ENGINES = [
  "chatgpt",
  "google_ai_overviews",
  "google_ai_mode",
  "gemini",
  "perplexity",
  "claude",
  "copilot",
  "grok"
] as const;
export type AiEngine = (typeof AI_ENGINES)[number];

export const TASK_CLASSES = [
  "monitoring",
  "classification",
  "content_generation",
  "technical_fix",
  "citation_outreach",
  "strategy"
] as const;
export type TaskClass = (typeof TASK_CLASSES)[number];

export type CmsType = "wordpress" | "webflow" | "contentful" | "sanity" | "shopify";
export type UserRole = "owner" | "admin" | "member";
export type DomainStatus = "onboarding" | "active" | "paused";

export type OpportunityType = "content" | "technical" | "citation";
export type OpportunityStatus =
  | "proposed"
  | "approved"
  | "rejected"
  | "in_progress"
  | "done";

export interface PlanLimits {
  maxDomains: number | null;
  maxEngines: number;
  maxPromptsPerMonth: number | null;
  maxContentPerMonth: number | null;
  allowedAutonomyModes: readonly AutonomyMode[];
  tokenBudgetMonthly: number;
}

export const PLAN_LIMITS: Record<PlanTier, PlanLimits> = {
  operator: {
    maxDomains: 1,
    maxEngines: 5,
    maxPromptsPerMonth: 100,
    maxContentPerMonth: 8,
    allowedAutonomyModes: ["review"],
    tokenBudgetMonthly: 1_000_000
  },
  growth: {
    maxDomains: 3,
    maxEngines: 8,
    maxPromptsPerMonth: 500,
    maxContentPerMonth: 25,
    allowedAutonomyModes: ["review", "auto_publish"],
    tokenBudgetMonthly: 4_000_000
  },
  scale: {
    maxDomains: null,
    maxEngines: 10,
    maxPromptsPerMonth: 2_000,
    maxContentPerMonth: 75,
    allowedAutonomyModes: ["review", "auto_publish", "autopilot"],
    tokenBudgetMonthly: 12_000_000
  },
  agency: {
    maxDomains: null,
    maxEngines: 8,
    maxPromptsPerMonth: null,
    maxContentPerMonth: null,
    allowedAutonomyModes: ["review", "auto_publish", "autopilot"],
    tokenBudgetMonthly: 4_000_000
  },
  enterprise: {
    maxDomains: null,
    maxEngines: 10,
    maxPromptsPerMonth: null,
    maxContentPerMonth: null,
    allowedAutonomyModes: ["review", "auto_publish", "autopilot"],
    tokenBudgetMonthly: 20_000_000
  }
};

export interface TenantContext {
  orgId: string;
  domainId?: string;
  userId?: string;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  planTier: PlanTier;
  tokenBudgetMonthly: number;
  tokenUsedCurrentPeriod: number;
  autonomyDefault: AutonomyMode;
}

export interface DomainSummary {
  id: string;
  orgId: string;
  url: string;
  cmsType: CmsType;
  autonomyMode: AutonomyMode;
  status: DomainStatus;
  /** Brand-voice guidelines used when generating content for this domain. */
  brandVoice: string;
}

export interface UserSummary {
  id: string;
  orgId: string;
  email: string;
  role: UserRole;
}

export interface AuthenticatedTenant {
  user: UserSummary;
  organization: OrganizationSummary;
  activeDomain: DomainSummary;
}

export interface AgentHandle {
  agentId: string;
  domainId: string;
  status: "provisioning" | "active" | "paused" | "failed";
}

export interface AgentRunRequest {
  tenant: TenantContext & { domainId: string };
  taskClass: TaskClass;
  autonomyMode: AutonomyMode;
  dryRun: boolean;
}

export interface AgentRunResult {
  runId: string;
  status: "completed" | "needs_approval" | "failed";
  opportunityIds: string[];
  draftIds: string[];
  usageRecordIds: string[];
}

export interface ModelUsageRecord {
  id: string;
  orgId: string;
  domainId: string;
  taskClass: TaskClass;
  provider: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  createdAt: string;
}

export function isPlanTier(value: string): value is PlanTier {
  return (PLAN_TIERS as readonly string[]).includes(value);
}

export function assertAutonomyAllowed(planTier: PlanTier, mode: AutonomyMode) {
  if (!PLAN_LIMITS[planTier].allowedAutonomyModes.includes(mode)) {
    throw new Error(`${mode} is not allowed for ${planTier}`);
  }
}
