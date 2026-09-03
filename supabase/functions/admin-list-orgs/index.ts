import { requireAdmin, serviceClient } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { currentMonth, fileLimitForPlan } from "../_shared/plans.ts";

Deno.serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    if (req.method !== "GET") {
      return errorResponse("Method not allowed", 405);
    }

    await requireAdmin(req);
    const admin = serviceClient();
    const month = currentMonth();

    const { data: orgs, error: orgsError } = await admin
      .from("organizations")
      .select("id, name, plan, created_at")
      .order("created_at", { ascending: false });

    if (orgsError) {
      console.error(orgsError);
      return errorResponse("Failed to load organizations", 500);
    }

    const { data: profiles, error: profilesError } = await admin
      .from("profiles")
      .select("org_id, email, last_active_at")
      .eq("role", "owner");

    if (profilesError) {
      console.error(profilesError);
      return errorResponse("Failed to load profiles", 500);
    }

    const { data: usageRows, error: usageError } = await admin
      .from("usage_monthly")
      .select("org_id, files_processed")
      .eq("month", month);

    if (usageError) {
      console.error(usageError);
      return errorResponse("Failed to load usage", 500);
    }

    const { data: devices, error: devicesError } = await admin
      .from("devices")
      .select("org_id");

    if (devicesError) {
      console.error(devicesError);
      return errorResponse("Failed to load devices", 500);
    }

    const profileByOrg = new Map(
      (profiles ?? []).map((p) => [p.org_id as string, p]),
    );
    const usageByOrg = new Map(
      (usageRows ?? []).map((u) => [u.org_id as string, u.files_processed as number]),
    );
    const deviceCountByOrg = new Map<string, number>();
    for (const device of devices ?? []) {
      const orgId = device.org_id as string;
      deviceCountByOrg.set(orgId, (deviceCountByOrg.get(orgId) ?? 0) + 1);
    }

    const result = (orgs ?? []).map((org) => {
      const profile = profileByOrg.get(org.id as string);
      const plan = org.plan as string;
      return {
        id: org.id,
        name: org.name,
        plan,
        email: profile?.email ?? "",
        files_used: usageByOrg.get(org.id as string) ?? 0,
        file_limit: fileLimitForPlan(plan),
        last_active_at: profile?.last_active_at ?? null,
        device_count: deviceCountByOrg.get(org.id as string) ?? 0,
        created_at: org.created_at,
      };
    });

    return jsonResponse({ orgs: result });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
