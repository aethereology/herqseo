import { NextResponse } from "next/server";
import { leadSink, publicAuditStore } from "../../../../lib/public-audit";

export const dynamic = "force-dynamic";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    email?: string;
    token?: string;
    domainUrl?: string;
  };
  const email = (body.email ?? "").trim();
  if (!EMAIL.test(email)) {
    return NextResponse.json({ error: "A valid email is required." }, { status: 400 });
  }

  const store = publicAuditStore();
  // Unlock path: a report was generated and is cached under this token.
  const report = body.token ? store.getReport(body.token) : null;

  await leadSink().save({
    email,
    domainUrl: body.domainUrl ?? report?.domain_url ?? "",
    source: report ? "report-unlock" : "capacity-gate",
    createdAt: new Date().toISOString()
  });

  if (report) {
    return NextResponse.json({ report });
  }
  // Capacity-gated request: no report to return; we'll follow up by email.
  return NextResponse.json({ queued: true });
}
