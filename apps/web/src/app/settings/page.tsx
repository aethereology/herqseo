import Link from "next/link";
import { requireTenant } from "../../lib/tenant";
import { WordPressSettings } from "./WordPressSettings";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const tenant = await requireTenant();

  return (
    <main className="min-h-screen bg-paper">
      <section className="border-b border-line bg-white">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-5 py-6 sm:px-8">
          <Link href="/" className="text-sm font-semibold text-moss underline">
            Back to operator loop
          </Link>
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-moss">
              {tenant.organization.name}
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-ink">Settings</h1>
            <p className="mt-2 text-sm text-ink/60">{tenant.activeDomain.url}</p>
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-5xl px-5 py-7 sm:px-8">
        <WordPressSettings defaultUrl={tenant.activeDomain.url} />
      </section>
    </main>
  );
}
