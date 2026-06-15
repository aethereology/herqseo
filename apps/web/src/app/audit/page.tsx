import Link from "next/link";
import { requireTenant } from "../../lib/tenant";
import { AuditRunner } from "./AuditRunner";

export const dynamic = "force-dynamic";

export default async function AuditPage() {
  const tenant = await requireTenant();

  return (
    <main className="mx-auto w-full max-w-5xl px-5 py-8 sm:px-8 lg:px-10">
      <div className="flex items-center justify-between print:hidden">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-moss">
            {tenant.organization.name}
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">AI Search Audit</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink/70">
            Paste any website. We crawl it, check on-page technical readiness, test whether AI
            answers cite the brand for buyer-intent queries, and draft one sample fix.
          </p>
        </div>
        <Link
          href="/"
          className="rounded border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-paper"
        >
          ← Dashboard
        </Link>
      </div>

      <div className="mt-6">
        <AuditRunner defaultUrl={tenant.activeDomain.url} />
      </div>
    </main>
  );
}
