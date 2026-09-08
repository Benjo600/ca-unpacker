import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { errorResponse } from "./cors.ts";

export function userClient(req: Request) {
  const auth = req.headers.get("Authorization") ?? "";
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: auth } } },
  );
}

export function serviceClient() {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
}

export async function requireUser(req: Request) {
  const supabase = userClient(req);
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) {
    throw errorResponse("Unauthorized", 401);
  }
  return { supabase, user: data.user };
}

export async function requireAdmin(req: Request) {
  const { user } = await requireUser(req);
  const allowed = (Deno.env.get("ADMIN_ALLOWED_EMAILS") ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  if (!allowed.includes((user.email ?? "").toLowerCase())) {
    throw errorResponse("Forbidden", 403);
  }
  return user;
}

export async function loadUserOrg(userId: string) {
  const admin = serviceClient();
  const { data: profile, error: profileError } = await admin
    .from("profiles")
    .select("org_id")
    .eq("id", userId)
    .single();

  if (profileError || !profile) {
    throw errorResponse("Profile not found", 404);
  }

  const { data: org, error: orgError } = await admin
    .from("organizations")
    .select("plan")
    .eq("id", profile.org_id)
    .single();

  if (orgError || !org) {
    throw errorResponse("Organization not found", 404);
  }

  return { orgId: profile.org_id as string, plan: org.plan as string };
}
