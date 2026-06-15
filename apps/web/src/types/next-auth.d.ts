import type { AuthenticatedTenant } from "@queryclear/shared";
import type { DefaultSession } from "next-auth";
import type { JWT as DefaultJWT } from "next-auth/jwt";

declare module "next-auth" {
  interface Session extends DefaultSession {
    tenant?: AuthenticatedTenant;
  }

  interface User {
    tenant?: AuthenticatedTenant;
  }
}

declare module "next-auth/jwt" {
  interface JWT extends DefaultJWT {
    tenant?: AuthenticatedTenant;
  }
}
