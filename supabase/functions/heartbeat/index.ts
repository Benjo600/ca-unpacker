import { requireUser, loadUserOrg, serviceClient } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import {
  parseJsonBody,
  rejectExtraKeys,
  requireString,
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
    rejectExtraKeys(body, [
      "app_version",
      "device_label",
      "fingerprint_sha256",
    ]);

    if (
      !("app_version" in body) ||
      !("device_label" in body) ||
      !("fingerprint_sha256" in body)
    ) {
      return errorResponse(
        "app_version, device_label, and fingerprint_sha256 are required",
        400,
      );
    }

    const appVersion = requireString(body.app_version, "app_version");
    const deviceLabel = requireString(body.device_label, "device_label");
    const fingerprintSha256 = requireString(
      body.fingerprint_sha256,
      "fingerprint_sha256",
    );
    const { orgId } = await loadUserOrg(user.id);
    const admin = serviceClient();
    const now = new Date().toISOString();

    const { error: deviceError } = await admin.from("devices").upsert(
      {
        org_id: orgId,
        user_id: user.id,
        fingerprint_sha256: fingerprintSha256,
        label: deviceLabel,
        app_version: appVersion,
        last_seen_at: now,
        active: true,
      },
      { onConflict: "org_id,fingerprint_sha256" },
    );

    if (deviceError) {
      console.error(deviceError);
      return errorResponse("Failed to update device", 500);
    }

    const { error: profileError } = await admin
      .from("profiles")
      .update({ last_active_at: now })
      .eq("id", user.id);

    if (profileError) {
      console.error(profileError);
      return errorResponse("Failed to update profile", 500);
    }

    return jsonResponse({ ok: true });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
