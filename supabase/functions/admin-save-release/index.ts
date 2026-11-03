import { requireAdmin, serviceClient } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { parseJsonBody } from "../_shared/validate.ts";
import { parseReleaseInput, type ReleaseDraftInput } from "../_shared/releases.ts";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

Deno.serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    if (req.method !== "POST") return errorResponse("Method not allowed", 405);
    const user = await requireAdmin(req);
    const body = await parseJsonBody(req);

    let input: ReleaseDraftInput;
    try {
      input = parseReleaseInput(body);
    } catch (err) {
      return errorResponse(err instanceof Error ? err.message : "Invalid release", 400);
    }

    let releaseId: string | null = null;
    if (typeof body.id !== "undefined" && body.id !== null) {
      if (typeof body.id !== "string" || !UUID_RE.test(body.id)) {
        return errorResponse("id must be a valid release id", 400);
      }
      releaseId = body.id;
    }

    const admin = serviceClient();
    const { data, error } = await admin.rpc("admin_save_release", {
      p_id: releaseId,
      p_version: input.version,
      p_title: input.title,
      p_release_notes: input.release_notes,
      p_installer_url: input.installer_url,
      p_installer_sha256: input.installer_sha256,
      p_installer_size: input.installer_size,
      p_mandatory: input.mandatory,
      p_minimum_supported_version: input.minimum_supported_version,
      p_actor: user.email ?? "unknown",
    });

    if (error) {
      const code = String(error.code ?? "");
      if (code === "P0001") return errorResponse("Only drafts can be edited", 409);
      if (code === "P0002") return errorResponse("Release not found", 404);
      if (code === "22023" || code === "23505" || code === "23514") {
        return errorResponse(error.message || "Invalid release", 400);
      }
      console.error(error);
      return errorResponse("Failed to save the release", 500);
    }

    return jsonResponse({ ok: true, release_id: data, status: "draft" });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
