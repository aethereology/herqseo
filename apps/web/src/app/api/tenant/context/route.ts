import { NextResponse } from "next/server";
import { auth } from "../../../../../auth";

export async function GET() {
  const session = await auth();

  if (!session?.tenant) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  return NextResponse.json({ tenant: session.tenant });
}
