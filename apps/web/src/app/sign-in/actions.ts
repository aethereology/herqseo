"use server";

import { AuthError } from "next-auth";
import { signIn, signOut } from "../../../auth";

export async function signInWithCredentials(
  _previousState: string | null,
  formData: FormData
) {
  try {
    await signIn("credentials", {
      email: formData.get("email"),
      code: formData.get("code"),
      redirectTo: "/"
    });
  } catch (error) {
    if (error instanceof AuthError) {
      return "Invalid email or access code.";
    }

    throw error;
  }

  return null;
}

export async function signOutOfDashboard() {
  await signOut({ redirectTo: "/sign-in" });
}
