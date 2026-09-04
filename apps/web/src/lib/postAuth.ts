import type { Session } from "@supabase/supabase-js";
import {
  defaultSignedInPath,
  isSafeNextPath,
  redirectToDesktop,
} from "./admin";

export async function pathAfterAuth(
  session: Session | null,
  searchParams: URLSearchParams,
): Promise<"desktop" | string> {
  if (searchParams.get("redirect") === "desktop" && session) {
    redirectToDesktop(session);
    return "desktop";
  }

  const next = searchParams.get("next");
  if (isSafeNextPath(next)) {
    return next;
  }

  return defaultSignedInPath();
}
