import { supabase } from "./supabase";

export type PlanType = "starter" | "pro" | "suspended";

export interface AdminOrg {
  id: string;
  name: string;
  plan: PlanType;
  email: string;
  files_used: number;
  file_limit: number | null;
  last_active_at: string | null;
  device_count: number;
  created_at: string;
}

export interface AdminListResponse {
  orgs: AdminOrg[];
}

export interface AdminUpdatePlanResponse {
  ok: boolean;
  plan: PlanType;
}

function functionsBaseUrl(): string {
  return `${import.meta.env.VITE_SUPABASE_URL}/functions/v1`;
}

async function authHeaders(): Promise<HeadersInit> {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    throw new Error("Not signed in");
  }

  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

export async function fetchAdminOrgs(): Promise<AdminOrg[]> {
  const res = await fetch(`${functionsBaseUrl()}/admin-list-orgs`, {
    headers: await authHeaders(),
  });

  if (res.status === 403) {
    throw new AdminForbiddenError();
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Failed to load organizations (${res.status})`);
  }

  const data = (await res.json()) as AdminListResponse;
  return data.orgs;
}

export async function updateOrgPlan(
  orgId: string,
  plan: PlanType,
): Promise<AdminUpdatePlanResponse> {
  const res = await fetch(`${functionsBaseUrl()}/admin-update-plan`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({ org_id: orgId, plan }),
  });

  if (res.status === 403) {
    throw new AdminForbiddenError();
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Failed to update plan (${res.status})`);
  }

  return (await res.json()) as AdminUpdatePlanResponse;
}

export class AdminForbiddenError extends Error {
  constructor() {
    super("Not an admin");
    this.name = "AdminForbiddenError";
  }
}

export function formatFileLimit(limit: number | null): string {
  return limit === null ? "unlimited" : String(limit);
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function isActiveWithinDays(
  lastActiveAt: string | null,
  days: number,
): boolean {
  if (!lastActiveAt) return false;
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  return new Date(lastActiveAt).getTime() >= cutoff;
}

export function currentMonthLabel(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function redirectToDesktop(session: {
  access_token: string;
  refresh_token: string;
}): void {
  const { access_token, refresh_token } = session;
  window.location.href = `caunpacker://auth/callback#access_token=${encodeURIComponent(access_token)}&refresh_token=${encodeURIComponent(refresh_token)}`;
}
