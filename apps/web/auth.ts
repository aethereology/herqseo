import NextAuth, { type NextAuthConfig, type NextAuthResult } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import {
  AUTONOMY_MODE_KEYS,
  isPlanTier,
  PLAN_LIMITS,
  type AuthenticatedTenant,
  type AutonomyMode,
  type CmsType,
  type DomainStatus,
  type PlanTier,
  type UserRole
} from "@queryclear/shared";

function requiredEnv(name: string, fallback: string) {
  return process.env[name] ?? fallback;
}

function readPlanTier(value: string | undefined): PlanTier {
  return value && isPlanTier(value) ? value : "operator";
}

function readAutonomyMode(value: string | undefined): AutonomyMode {
  return value && (AUTONOMY_MODE_KEYS as readonly string[]).includes(value)
    ? (value as AutonomyMode)
    : "review";
}

function buildDevTenant(email: string): AuthenticatedTenant {
  const planTier = readPlanTier(process.env.QUERYCLEAR_DEV_PLAN_TIER);
  const plan = PLAN_LIMITS[planTier];
  const orgId = requiredEnv("QUERYCLEAR_DEV_ORG_ID", "org_dev_queryclear");
  const domainId = requiredEnv("QUERYCLEAR_DEV_DOMAIN_ID", "domain_dev_queryclear");

  return {
    user: {
      id: requiredEnv("QUERYCLEAR_DEV_USER_ID", "user_dev_owner"),
      orgId,
      email,
      role: (process.env.QUERYCLEAR_DEV_USER_ROLE as UserRole | undefined) ?? "owner"
    },
    organization: {
      id: orgId,
      name: requiredEnv("QUERYCLEAR_DEV_ORG_NAME", "QueryClear Demo"),
      planTier,
      tokenBudgetMonthly: plan.tokenBudgetMonthly,
      tokenUsedCurrentPeriod: Number(process.env.QUERYCLEAR_DEV_TOKEN_USED ?? "0"),
      autonomyDefault: readAutonomyMode(process.env.QUERYCLEAR_DEV_AUTONOMY_MODE)
    },
    activeDomain: {
      id: domainId,
      orgId,
      url: requiredEnv("QUERYCLEAR_DEV_DOMAIN_URL", "https://example-b2b-saas.com"),
      cmsType: (process.env.QUERYCLEAR_DEV_CMS_TYPE as CmsType | undefined) ?? "wordpress",
      autonomyMode: readAutonomyMode(process.env.QUERYCLEAR_DEV_AUTONOMY_MODE),
      status: (process.env.QUERYCLEAR_DEV_DOMAIN_STATUS as DomainStatus | undefined) ?? "onboarding",
      // Empty = let the runtime derive (and cache) the voice from the site.
      // Set a non-empty value to pin an explicit per-domain voice instead.
      brandVoice: process.env.QUERYCLEAR_DEV_BRAND_VOICE ?? ""
    }
  };
}

export const authConfig = {
  pages: {
    signIn: "/sign-in"
  },
  trustHost: process.env.AUTH_TRUST_HOST === "true" || process.env.NODE_ENV !== "production",
  session: {
    strategy: "jwt"
  },
  providers: [
    Credentials({
      name: "Development credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        code: { label: "Access code", type: "password" }
      },
      authorize(credentials) {
        const email = String(credentials?.email ?? "").trim().toLowerCase();
        const code = String(credentials?.code ?? "");
        const allowedEmail = requiredEnv("QUERYCLEAR_DEV_USER_EMAIL", "operator@queryclear.dev")
          .trim()
          .toLowerCase();
        const allowedCode = requiredEnv("QUERYCLEAR_DEV_LOGIN_CODE", "queryclear-dev");

        if (email !== allowedEmail || code !== allowedCode) {
          return null;
        }

        const tenant = buildDevTenant(email);
        return {
          id: tenant.user.id,
          email: tenant.user.email,
          name: tenant.organization.name,
          tenant
        };
      }
    })
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user && "tenant" in user) {
        token.tenant = user.tenant;
      }
      return token;
    },
    session({ session, token }) {
      session.tenant = token.tenant;
      return session;
    }
  }
} satisfies NextAuthConfig;

const nextAuth: NextAuthResult = NextAuth(authConfig);

export const auth: NextAuthResult["auth"] = nextAuth.auth;
export const handlers: NextAuthResult["handlers"] = nextAuth.handlers;
export const signIn: NextAuthResult["signIn"] = nextAuth.signIn;
export const signOut: NextAuthResult["signOut"] = nextAuth.signOut;
