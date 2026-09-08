import { requireUser, loadUserOrg } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { currentMonth, fileLimitForPlan } from "../_shared/plans.ts";
import { loadMonthlyUsage } from "../_shared/usage.ts";
import {
  parseJsonBody,
  rejectExtraKeys,
  requireNonNegativeInt,
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
    rejectExtraKeys(body, ["file_count"]);

    if (!("file_count" in body)) {
      return errorResponse("file_count is required", 400);
    }

    const fileCount = requireNonNegativeInt(body.file_count, "file_count");
    const { orgId, plan } = await loadUserOrg(user.id);

    if (plan === "suspended") {
      return errorResponse("Account suspended", 403);
    }

    const filesUsed = await loadMonthlyUsage(orgId, currentMonth());
    const fileLimit = fileLimitForPlan(plan);
    const allowed = fileLimit === null || filesUsed + fileCount <= fileLimit;

    return jsonResponse({
      allowed,
      files_used: filesUsed,
      file_limit: fileLimit,
      plan,
    });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
