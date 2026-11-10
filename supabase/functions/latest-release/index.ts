import { requireUser, serviceClient } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { parseJsonBody } from "../_shared/validate.ts";
import {
  isSupportedArch,
  isSupportedPlatform,
  parseVersion,
  publicRelease,
  selectLatestRelease,
  type ReleaseRecord,
} from "../_shared/releases.ts";

Deno.serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    if (req.method !== "POST") return errorResponse("Method not allowed", 405);
    await requireUser(req);
    const body = await parseJsonBody(req);

    const allowed = ["current_version", "platform", "arch"];
    for (const key of Object.keys(body)) {
      if (!allowed.includes(key)) {
        return errorResponse(`Unexpected field: ${key}`, 400);
      }
    }
    if (!allowed.every((key) => key in body)) {
      return errorResponse("current_version, platform and arch are required", 400);
    }

    let currentVersion: string;
    try {
      currentVersion = parseVersion(body.current_version);
    } catch (err) {
      return errorResponse(
        err instanceof Error ? err.message : "current_version is invalid",
        400,
      );
    }
    if (!isSupportedPlatform(body.platform)) {
      return jsonResponse({ update_available: false });
    }
    if (!isSupportedArch(body.arch)) {
      return errorResponse("arch must be x64 or arm64", 400);
    }

    const admin = serviceClient();
    const { data, error } = await admin
      .from("app_releases")
      .select("*")
      .eq("status", "published")
      .maybeSingle();

    if (error) {
      console.error(error);
      return errorResponse("Failed to check for updates", 500);
    }

    const selected = selectLatestRelease(
      currentVersion,
      (data as ReleaseRecord | null) ?? null,
    );
    if (!selected) return jsonResponse({ update_available: false });

    return jsonResponse({
      update_available: true,
      release: publicRelease(selected),
    });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
