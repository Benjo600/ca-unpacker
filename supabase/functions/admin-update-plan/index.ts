import { requireAdmin, serviceClient } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { VALID_PLANS } from "../_shared/plans.ts";
import { parseJsonBody, rejectExtraKeys } from "../_shared/validate.ts";

Deno.serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    if (req.method !== "POST") {
      return errorResponse("Method not allowed", 405);
    }

    await requireAdmin(req);
    const body = await parseJsonBody(req);
    rejectExtraKeys(body, ["org_id", "plan"]);

    if (!("org_id" in body) || !("plan" in body)) {
      return errorResponse("org_id and plan are required", 400);
    }

    const orgId = body.org_id;
    const plan = body.plan;

    if (typeof orgId !== "string" || orgId.trim() === "") {
      return errorResponse("org_id must be a non-empty string", 400);
    }

    if (typeof plan !== "string" || !VALID_PLANS.includes(plan as typeof VALID_PLANS[number])) {
      return errorResponse("plan must be starter, pro, or suspended", 400);
    }

    const admin = serviceClient();
    const now = new Date().toISOString();

    const { data, error } = await admin
      .from("organizations")
      .update({ plan, updated_at: now })
      .eq("id", orgId)
      .select("plan")
      .maybeSingle();

    if (error) {
      console.error(error);
      return errorResponse("Failed to update plan", 500);
    }

    if (!data) {
      return errorResponse("Organization not found", 404);
    }

    return jsonResponse({ ok: true, plan: data.plan });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
