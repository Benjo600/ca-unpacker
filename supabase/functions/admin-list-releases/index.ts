import { requireAdmin, serviceClient } from "../_shared/auth.ts";
import {
  errorResponse,
  handleCors,
  jsonResponse,
  withCors,
} from "../_shared/cors.ts";
import { parseJsonBody } from "../_shared/validate.ts";
import { compareVersions } from "../_shared/releases.ts";

Deno.serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    if (req.method !== "POST") return errorResponse("Method not allowed", 405);
    await requireAdmin(req);
    const body = await parseJsonBody(req);
    if (Object.keys(body).length > 0) {
      return errorResponse("This endpoint takes no fields", 400);
    }

    const admin = serviceClient();
    const { data, error } = await admin.from("app_releases").select("*");
    if (error) {
      console.error(error);
      return errorResponse("Failed to load releases", 500);
    }

    const releases = (data ?? []).slice().sort((a, b) => {
      try {
        const byVersion = compareVersions(String(b.version), String(a.version));
        if (byVersion !== 0) return byVersion;
      } catch {
        // fall through to created_at
      }
      return String(b.created_at ?? "").localeCompare(String(a.created_at ?? ""));
    });

    return jsonResponse({ releases });
  } catch (err) {
    if (err instanceof Response) return withCors(err);
    console.error(err);
    return errorResponse("Internal server error", 500);
  }
});
