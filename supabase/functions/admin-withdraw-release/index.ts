import { requireAdmin, serviceClient } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { parseJsonBody } from "../_shared/validate.ts";
import { requireReleaseId } from "../_shared/releases.ts";

Deno.serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    if (req.method !== "POST") return errorResponse("Method not allowed", 405);
    const user = await requireAdmin(req);
    const body = await parseJsonBody(req);

    let releaseId: string;
    try {
      releaseId = requireReleaseId(body);
    } catch (err) {
      return errorResponse(err instanceof Error ? err.message : "Invalid request", 400);
    }

    const admin = serviceClient();
    const { data: release, error: loadError } = await admin
      .from("app_releases")
      .select("id, status")
      .eq("id", releaseId)
      .maybeSingle();

    if (loadError) {
      console.error(loadError);
      return errorResponse("Failed to load the release", 500);
    }
    if (!release) return errorResponse("Release not found", 404);
    if (release.status !== "published") {
      return errorResponse("Only a published release can be withdrawn", 409);
    }

    const { error } = await admin.rpc("admin_withdraw_release", {
      p_id: releaseId,
      p_actor: user.email ?? "unknown",
    });
    if (error) {
      const code = String(error.code ?? "");
      if (code === "P0001") return errorResponse("Release is not published", 409);
      if (code === "P0002") return errorResponse("Release not found", 404);
      console.error(error);
      return errorResponse("Failed to withdraw the release", 500);
    }

    return jsonResponse({ ok: true, release_id: releaseId, status: "withdrawn" });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
