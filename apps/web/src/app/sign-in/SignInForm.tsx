"use client";

import { useActionState } from "react";
import { signInWithCredentials } from "./actions";

export function SignInForm() {
  const [error, formAction, pending] = useActionState(signInWithCredentials, null);

  return (
    <form action={formAction} className="mt-8 grid gap-4">
      <label className="grid gap-2 text-sm font-medium text-ink">
        Email
        <input
          className="rounded border border-line bg-white px-3 py-2 text-base font-normal outline-none ring-lime/40 transition focus:ring-2"
          name="email"
          type="email"
          autoComplete="email"
          defaultValue="operator@queryclear.dev"
          required
        />
      </label>
      <label className="grid gap-2 text-sm font-medium text-ink">
        Access code
        <input
          className="rounded border border-line bg-white px-3 py-2 text-base font-normal outline-none ring-lime/40 transition focus:ring-2"
          name="code"
          type="password"
          autoComplete="current-password"
          defaultValue="queryclear-dev"
          required
        />
      </label>
      {error ? <p className="text-sm font-medium text-red-700">{error}</p> : null}
      <button
        className="rounded bg-ink px-4 py-2.5 text-sm font-semibold text-paper transition hover:bg-moss disabled:cursor-not-allowed disabled:opacity-60"
        type="submit"
        disabled={pending}
      >
        {pending ? "Signing in..." : "Sign in"}
      </button>
    </form>
  );
}
