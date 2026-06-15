import {
  AUTONOMY_MODES,
  AI_ENGINES,
  PLAN_LIMITS,
  type AutonomyMode
} from "@queryclear/shared";
import { requireTenant } from "../lib/tenant";
import { signOutOfDashboard } from "./sign-in/actions";
import { OperatorConsole } from "./OperatorConsole";

export const dynamic = "force-dynamic";

const workflow = [
  { label: "Crawl", value: "1 domain", detail: "B2B SaaS site baseline" },
  { label: "Monitor", value: "5 engines", detail: "Prompt evidence captured" },
  { label: "Draft", value: "1 piece", detail: "Answer-first content" },
  { label: "Approve", value: "Review", detail: "Human gate before publish" }
];

export default async function Home() {
  const tenant = await requireTenant();
  const activePlan = tenant.organization.planTier;
  const activeMode: AutonomyMode = tenant.activeDomain.autonomyMode;
  const plan = PLAN_LIMITS[activePlan];
  const contentLimit =
    plan.maxContentPerMonth === null ? "Unlimited" : plan.maxContentPerMonth.toString();
  const tokenUsed = tenant.organization.tokenUsedCurrentPeriod.toLocaleString();
  const tokenBudget = tenant.organization.tokenBudgetMonthly.toLocaleString();

  return (
    <main className="min-h-screen">
      <section className="border-b border-line bg-paper">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-5 py-6 sm:px-8 lg:px-10">
          <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-moss">
                {tenant.organization.name}
              </p>
              <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight text-ink sm:text-5xl">
                Operator loop for one domain, one draft, one approval gate.
              </h1>
              <div className="mt-5 flex flex-wrap gap-2 text-sm text-ink/70">
                <span className="rounded border border-line bg-white px-2.5 py-1">
                  {tenant.activeDomain.url}
                </span>
                <span className="rounded border border-line bg-white px-2.5 py-1 capitalize">
                  {tenant.user.role}
                </span>
                <span className="rounded border border-line bg-white px-2.5 py-1">
                  {tenant.user.email}
                </span>
              </div>
            </div>
            <div className="grid gap-3 rounded border border-line bg-white p-4 sm:grid-cols-2 lg:min-w-80">
              <Metric label="Plan" value={activePlan} capitalize />
              <Metric label="Mode" value={AUTONOMY_MODES[activeMode].label} />
              <Metric label="Tokens used" value={`${tokenUsed} / ${tokenBudget}`} />
              <Metric label="Content/mo" value={contentLimit} />
              <form action={signOutOfDashboard} className="sm:col-span-2">
                <button
                  className="w-full rounded border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-paper"
                  type="submit"
                >
                  Sign out
                </button>
              </form>
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
        <OperatorConsole
          domainUrl={tenant.activeDomain.url}
          brand={tenant.organization.name}
          autonomyModeLabel={AUTONOMY_MODES[activeMode].label}
        />

        <aside className="rounded border border-line bg-ink p-5 text-paper">
          <h2 className="text-xl font-semibold">Guardrails</h2>
          <div className="mt-5 space-y-4">
            <Guardrail label="Autonomy" value={AUTONOMY_MODES[activeMode].label} />
            <Guardrail label="Engines" value={AI_ENGINES.slice(0, plan.maxEngines).join(", ")} />
            <Guardrail label="Publish target" value="Staging or draft only" />
            <Guardrail label="Tenant" value={`${tenant.organization.id} / ${tenant.activeDomain.id}`} />
            <Guardrail label="Budget rule" value="Meter before every model call" />
          </div>
        </aside>
      </section>
    </main>
  );
}

function Metric({
  label,
  value,
  capitalize = false
}: {
  label: string;
  value: string;
  capitalize?: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-moss">{label}</div>
      <div className={`mt-1 text-lg font-semibold text-ink ${capitalize ? "capitalize" : ""}`}>
        {value}
      </div>
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
