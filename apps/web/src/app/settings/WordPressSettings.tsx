"use client";

import { useEffect, useState } from "react";
import type {
  WordPressConnectResponse,
  WordPressStatusResponse
} from "../../lib/agent-runtime";

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "content-type": "application/json", ...init.headers },
    cache: "no-store"
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error((data as { error?: string }).error ?? "Request failed");
  }
  return data as T;
}

export function WordPressSettings({ defaultUrl }: { defaultUrl: string }) {
  const [baseUrl, setBaseUrl] = useState(defaultUrl);
  const [username, setUsername] = useState("");
  const [appPassword, setAppPassword] = useState("");
  const [status, setStatus] = useState<WordPressStatusResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    request<WordPressStatusResponse>("/api/integrations/wordpress/status")
      .then((next) => {
        setStatus(next);
        if (next.base_url) setBaseUrl(next.base_url);
        if (next.username) setUsername(next.username);
      })
      .catch(() => setStatus({ connected: false }));
  }, []);

  async function connect(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await request<WordPressConnectResponse>(
        "/api/integrations/wordpress/connect",
        {
          method: "POST",
          body: JSON.stringify({ baseUrl, username, appPassword })
        }
      );
      setStatus({
        connected: true,
        base_url: result.base_url,
        username: result.username
      });
      setAppPassword("");
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "WordPress connection failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded border border-line bg-white">
      <div className="border-b border-line px-5 py-4">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-xl font-semibold text-ink">WordPress</h2>
            <p className="mt-1 text-sm text-ink/60">
              Connect a self-hosted WordPress site for draft-only publishing.
            </p>
          </div>
          <span
            className={`w-fit rounded border px-2.5 py-1 text-xs font-semibold uppercase ${
              status?.connected
                ? "border-moss/40 bg-moss/10 text-moss"
                : "border-line bg-paper text-ink/55"
            }`}
          >
            {status?.connected ? "connected" : "not connected"}
          </span>
        </div>
      </div>

      <form onSubmit={connect} className="grid gap-4 px-5 py-5">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-moss">
              WordPress URL
            </span>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              required
              placeholder="https://example.com"
              className="mt-1 w-full rounded border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-moss"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-moss">
              Username
            </span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              className="mt-1 w-full rounded border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-moss"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-moss">
              Application password
            </span>
            <input
              value={appPassword}
              onChange={(e) => setAppPassword(e.target.value)}
              required
              type="password"
              autoComplete="current-password"
              className="mt-1 w-full rounded border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-moss"
            />
          </label>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink/60">
            The check verifies REST JSON, credentials, and app-password support before saving.
          </p>
          <button
            type="submit"
            disabled={busy}
            aria-busy={busy}
            className="rounded bg-ink px-4 py-2 text-sm font-semibold text-paper transition hover:bg-ink/90 disabled:opacity-60"
          >
            {busy ? "Connecting…" : "Save connection"}
          </button>
        </div>

        {message ? <p className="text-sm font-medium text-moss">{message}</p> : null}
        {error ? (
          <p className="rounded border border-line bg-paper px-3 py-2 text-sm text-ink">
            <span className="font-semibold text-moss">Fix needed:</span> {error}
          </p>
        ) : null}
      </form>
    </section>
  );
}
