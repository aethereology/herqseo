import { redirect } from "next/navigation";
import { auth } from "../../auth";

export async function requireTenant() {
  const session = await auth();

  if (!session?.tenant) {
    redirect("/sign-in");
  }

  return session.tenant;
}
