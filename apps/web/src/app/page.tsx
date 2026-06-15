import {
  AUTONOMY_MODES,
  AI_ENGINES,
  PLAN_LIMITS,
  type AutonomyMode,
  type PlanTier
} from "@queryclear/shared";

const activePlan: PlanTier = "operator";
const activeMode: AutonomyMode = "review";
const plan = PLAN_LIMITS[activePlan];
const contentLimit =
  plan.maxContentPerMonth === null ? "Unlimited" : plan.maxContentPerMonth.toString();

const workflow = [
  { label: "Crawl", value: "1 domain", detail: "B2B SaaS site baseline" },
  { label: "Monitor", value: "5 engines", detail: "Prompt evidence captured" },
  { label: "Draft", value: "1 piece", detail: "Answer-first content" },
  { label: "Approve", value: "Review", detail: "Human gate before publish" }
];

const opportunities = [
  {
    title: "Comparison page gap",
    evidence: "Perplexity and ChatGPT cite competitors for buying-stage prompts.",
    status: "Proposed"
  },
  {
    title: "FAQ schema missing",
    evidence: "Current product pages answer crawler questions without structured data.",
    status: "Ready for review"
  },
  {
    title: "llms.txt draft",
    evidence: "Crawler guidance is absent; generated draft is waiting on approval.",
    status: "Draft"
  }
];

export default function Home() {
  return (
    <main className="min-h-screen">
      <section className="border-b border-line bg-paper">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-5 py-6 sm:px-8 lg:px-10">
          <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-start">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-moss">
                QueryClear Control Plane
              </p>
              <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight text-ink sm:text-5xl">
                Operator loop for one domain, one draft, one approval gate.
              </h1>
            </div>
            <div className="grid min-w-64 grid-cols-2 gap-3 rounded border border-line bg-white p-4">
              <Metric label="Plan" value={activePlan} />
              <Metric label="Mode" value={activeMode} />
              <Metric label="Monthly tokens" value={plan.tokenBudgetMonthly.toLocaleString()} />
              <Metric label="Content/mo" value={contentLimit} />
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            {workflow.map((step) => (
              <div key={step.label} className="rounded border border-line bg-white p-4">
                <div className="text-sm font-medium text-moss">{step.label}</div>
                <div className="mt-2 text-2xl font-semibold text-ink">{step.value}</div>
                <div className="mt-3 text-sm leading-6 text-ink/70">{step.detail}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-7xl gap-6 px-5 py-7 sm:px-8 lg:grid-cols-[1.2fr_0.8fr] lg:px-10">
        <div className="rounded border border-line bg-white">
          <div className="border-b border-line px-5 py-4">
            <h2 className="text-xl font-semibold text-ink">Review Queue</h2>
          </div>
          <div className="divide-y divide-line">
            {opportunities.map((opportunity) => (
              <article key={opportunity.title} className="px-5 py-5">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <h3 className="text-lg font-semibold text-ink">{opportunity.title}</h3>
                  <span className="w-fit rounded border border-line px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-moss">
                    {opportunity.status}
                  </span>
                </div>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-ink/70">
                  {opportunity.evidence}
                </p>
              </article>
            ))}
          </div>
        </div>

        <aside className="rounded border border-line bg-ink p-5 text-paper">
          <h2 className="text-xl font-semibold">Guardrails</h2>
          <div className="mt-5 space-y-4">
            <Guardrail label="Autonomy" value={AUTONOMY_MODES[activeMode].label} />
            <Guardrail label="Engines" value={AI_ENGINES.slice(0, plan.maxEngines).join(", ")} />
            <Guardrail label="Publish target" value="Staging or draft only" />
            <Guardrail label="Budget rule" value="Meter before every model call" />
          </div>
        </aside>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-moss">{label}</div>
      <div className="mt-1 text-lg font-semibold capitalize text-ink">{value}</div>
    </div>
  );
}

function Guardrail({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-white/15 pb-4 last:border-0 last:pb-0">
      <div className="text-xs font-medium uppercase tracking-wide text-lime">{label}</div>
      <div className="mt-2 text-sm leading-6 text-paper/85">{value}</div>
    </div>
  );
}
