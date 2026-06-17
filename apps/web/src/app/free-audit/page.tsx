import { FreeAudit } from "./FreeAudit";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Free AI Search Audit — QueryClear",
  description:
    "See whether AI answer engines can find, understand, and cite your site. Free, read-only audit with a prioritized fix list."
};

export default function FreeAuditPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-12 sm:px-8">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-moss">QueryClear</p>
        <h1 className="mt-3 text-4xl font-semibold leading-tight text-ink">
          Can AI answer engines find and cite your site?
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-ink/70">
          Run a free, read-only audit. We check your on-page technical readiness, test whether AI
          assistants cite you for buyer-intent questions, and hand you a prioritized list of fixes —
          plus a sample draft written in your brand voice.
        </p>
      </header>

      <div className="mt-8">
        <FreeAudit />
      </div>

      <p className="mt-10 text-xs text-ink/45">
        We make your website easier for search engines and AI answer engines to understand, trust,
        and recommend. No fake guarantees — just clearer, AI-readable technical readiness.
      </p>
    </main>
  );
}
