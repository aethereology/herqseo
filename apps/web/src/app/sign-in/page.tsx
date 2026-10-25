import { redirect } from "next/navigation";
import { auth } from "../../../auth";
import { developmentAuthEnabled } from "../../lib/auth-policy";
import { SignInForm } from "./SignInForm";

export default async function SignInPage() {
  const enabled = developmentAuthEnabled();
  const session = enabled ? await auth() : null;

  if (session?.tenant) {
    redirect("/");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-5 py-10">
      <section className="w-full max-w-md rounded border border-line bg-white p-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-moss">
          QueryClear Operator
        </p>
        <h1 className="mt-3 text-3xl font-semibold leading-tight text-ink">
          {enabled ? "Sign in to the control plane." : "Operator access is not available yet."}
        </h1>
        <p className="mt-4 text-sm leading-6 text-ink/70">
          {enabled ? "Development credentials create a local test session. Do not connect customer accounts." : "This workspace is not open for customer sign-in. Production identity and organization membership must be configured before access is enabled."}
        </p>
        {enabled ? <SignInForm /> : null}
      </section>
    </main>
  );
}
