import { redirect } from "next/navigation";
import { auth } from "../../../auth";
import { SignInForm } from "./SignInForm";

export default async function SignInPage() {
  const session = await auth();

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
          Sign in to the control plane.
        </h1>
        <p className="mt-4 text-sm leading-6 text-ink/70">
          Development credentials create a tenant-scoped session for the first M0 loop.
        </p>
        <SignInForm />
      </section>
    </main>
  );
}
