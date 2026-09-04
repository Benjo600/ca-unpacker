import { fileLimitForPlan, type PlanType } from "./admin";
import { supabase } from "./supabase";

export interface UsageMonth {
  month: string;
  files_processed: number;
  clients_created: number;
  updated_at: string;
}

export interface AccountDevice {
  id: string;
  label: string;
  app_version: string;
  last_seen_at: string;
  active: boolean;
}

export interface AccountSnapshot {
  email: string;
  firmName: string;
  plan: PlanType;
  role: string;
  filesUsed: number;
  fileLimit: number | null;
  filesRemaining: number | null;
  month: string;
  lastActiveAt: string | null;
  createdAt: string;
  usageHistory: UsageMonth[];
  devices: AccountDevice[];
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export async function fetchAccountSnapshot(): Promise<AccountSnapshot> {
  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    throw new Error("Not signed in");
  }

  const { data: profile, error: profileError } = await supabase
    .from("profiles")
    .select("id, org_id, email, role, last_active_at, created_at")
    .eq("id", user.id)
    .maybeSingle();

  if (profileError) {
    throw new Error(profileError.message);
  }
  if (!profile) {
    throw new Error("Account profile is still being created. Refresh in a moment.");
  }

  const { data: org, error: orgError } = await supabase
    .from("organizations")
    .select("id, name, plan, created_at")
    .eq("id", profile.org_id)
    .maybeSingle();

  if (orgError) {
    throw new Error(orgError.message);
  }
  if (!org) {
    throw new Error("Firm record was not found.");
  }

  const { data: usageRows, error: usageError } = await supabase
    .from("usage_monthly")
    .select("month, files_processed, clients_created, updated_at")
    .eq("org_id", profile.org_id)
    .order("month", { ascending: false });

  if (usageError) {
    throw new Error(usageError.message);
  }

  const { data: deviceRows, error: deviceError } = await supabase
    .from("devices")
    .select("id, label, app_version, last_seen_at, active")
    .eq("user_id", user.id)
    .order("last_seen_at", { ascending: false });

  if (deviceError) {
    throw new Error(deviceError.message);
  }

  const plan = (org.plan as PlanType) || "starter";
  const month = currentMonth();
  const usageHistory = (usageRows ?? []) as UsageMonth[];
  const current = usageHistory.find((row) => row.month === month);
  const filesUsed = current?.files_processed ?? 0;
  const fileLimit = fileLimitForPlan(plan);
  const filesRemaining =
    fileLimit === null ? null : Math.max(0, fileLimit - filesUsed);

  return {
    email: profile.email || user.email || "",
    firmName: org.name,
    plan,
    role: profile.role,
    filesUsed,
    fileLimit,
    filesRemaining,
    month,
    lastActiveAt: profile.last_active_at,
    createdAt: org.created_at,
    usageHistory,
    devices: (deviceRows ?? []) as AccountDevice[],
  };
}
