import { requireAdmin, serviceClient } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { parseJsonBody } from "../_shared/validate.ts";
import {
  isApprovedInstallerUrl,
  normalizeChecksum,
  parseVersion,
  requirePositiveSize,
  requireReleaseId,
} from "../_shared/releases.ts";

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
      .select("*")
      .eq("id", releaseId)
      .maybeSingle();

    if (loadError) {
      console.error(loadError);
      return errorResponse("Failed to load the release", 500);
    }
    if (!release) return errorResponse("Release not found", 404);
    if (release.status !== "draft") {
      return errorResponse("Only a draft release can be published", 409);
    }

    try {
      parseVersion(release.version);
      normalizeChecksum(release.installer_sha256);
      requirePositiveSize(Number(release.installer_size));
      if (!isApprovedInstallerUrl(release.installer_url)) {
        throw new Error("Installer URL is not on an approved HTTPS host");
      }
      if (typeof release.title !== "string" || release.title.trim() === "") {
        throw new Error("Title is required");
      }
    } catch (err) {
      return errorResponse(
        err instanceof Error ? err.message : "Stored release is not valid",
        400,
      );
    }

    const { error } = await admin.rpc("admin_publish_release", {
      p_id: releaseId,
      p_actor: user.email ?? "unknown",
    });
    if (error) {
      const code = String(error.code ?? "");
      if (code === "P0001") return errorResponse("Release is no longer a draft", 409);
      if (code === "P0002") return errorResponse("Release not found", 404);
      console.error(error);
      return errorResponse("Failed to publish the release", 500);
    }

    return jsonResponse({ ok: true, release_id: releaseId, status: "published" });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
