import { requireUser, loadUserOrg } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { currentMonth, fileLimitForPlan } from "../_shared/plans.ts";
import { incrementMonthlyUsage } from "../_shared/usage.ts";
import {
  parseJsonBody,
  rejectExtraKeys,
  requirePositiveInt,
} from "../_shared/validate.ts";

Deno.serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    if (req.method !== "POST") {
      return errorResponse("Method not allowed", 405);
    }

    const { user } = await requireUser(req);
    const body = await parseJsonBody(req);
    rejectExtraKeys(body, ["files_processed"]);

    if (!("files_processed" in body)) {
      return errorResponse("files_processed is required", 400);
    }

    const filesProcessed = requirePositiveInt(
      body.files_processed,
      "files_processed",
    );
    const { orgId, plan } = await loadUserOrg(user.id);

    if (plan === "suspended") {
      return errorResponse("Account suspended", 403);
    }

    const filesUsed = await incrementMonthlyUsage(
      orgId,
      filesProcessed,
      currentMonth(),
    );

    return jsonResponse({
      files_used: filesUsed,
      file_limit: fileLimitForPlan(plan),
      plan,
    });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
