# Operator production readiness

The separate Operator application is a local development workspace, not a deployed customer dashboard. Development credentials are disabled when NODE_ENV=production or VERCEL/VERCEL_ENV is present. The production provider list is empty and JWT/session callbacks remove demo tenant identities. Login fields no longer ship prefilled credentials.

Before customer launch, implement a production identity provider and verified organization membership, persist membership/revocation checks, configure server-side secrets and tenant-scoped database access, and exercise authenticated browser journeys against an isolated staging environment. Do not expose the demo credentials provider as a substitute for customer authentication. No customer accounts or permissions were created by this change.

Validation: two authentication regression tests, workspace lint/typecheck, and 191 Python runtime cases (seven PostgreSQL cases run in their separate CI job). The public audit runtime remains separately deployed.

Framework maintenance: Next.js and its ESLint configuration are updated to 16.4.3 with compatible transitive fixes. The production dependency audit reports zero known vulnerabilities. Three moderate development-only advisories remain in the Tailwind 3 selector-parser chain; the suggested forced fix changes the styling toolchain and is deferred until Operator visual regression coverage exists.

Build from the repository root with `npm run build` so shared workspace packages are emitted before the Next.js application. Building only apps/web from a fresh checkout omits these prerequisites.
