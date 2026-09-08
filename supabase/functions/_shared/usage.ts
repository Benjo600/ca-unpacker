import { serviceClient } from "./auth.ts";
import { currentMonth } from "./plans.ts";
import { errorResponse } from "./cors.ts";

export async function loadMonthlyUsage(orgId: string, month = currentMonth()) {
  const { data, error } = await serviceClient()
    .from("usage_monthly")
    .select("files_processed")
    .eq("org_id", orgId)
    .eq("month", month)
    .maybeSingle();

  if (error) {
    throw errorResponse("Failed to load usage", 500);
  }

  return data?.files_processed ?? 0;
}

export async function incrementMonthlyUsage(
  orgId: string,
  filesProcessed: number,
  month = currentMonth(),
) {
  const admin = serviceClient();
  const current = await loadMonthlyUsage(orgId, month);
  const filesUsed = current + filesProcessed;
  const now = new Date().toISOString();

  const { error } = await admin.from("usage_monthly").upsert(
    {
      org_id: orgId,
      month,
      files_processed: filesUsed,
      updated_at: now,
    },
    { onConflict: "org_id,month" },
  );

  if (error) {
    throw errorResponse("Failed to record usage", 500);
  }

  return filesUsed;
}
