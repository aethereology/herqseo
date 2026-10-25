/** Demo identities are local-only; they are never production customer identity. */
export function developmentAuthEnabled(env: Record<string, string | undefined> = process.env): boolean {
  return env.NODE_ENV !== "production" && !env.VERCEL && !env.VERCEL_ENV;
}
