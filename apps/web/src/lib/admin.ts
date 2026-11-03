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

export type ReleaseStatus = "draft" | "published" | "withdrawn";

export interface AppRelease {
  id: string;
  version: string;
  title: string;
  release_notes: string;
  installer_url: string;
  installer_sha256: string;
  installer_size: number;
  status: ReleaseStatus;
  mandatory: boolean;
  minimum_supported_version: string | null;
  created_by: string | null;
  created_at: string;
  published_by: string | null;
  published_at: string | null;
  withdrawn_by: string | null;
  withdrawn_at: string | null;
}

export interface ReleaseDraft {
  version: string;
  title: string;
  release_notes: string;
  installer_url: string;
  installer_sha256: string;
  installer_size: number;
  mandatory: boolean;
  minimum_supported_version: string | null;
}

export interface AdminListReleasesResponse {
  releases: AppRelease[];
}

export interface AdminReleaseMutationResponse {
  ok: boolean;
  release_id: string;
  status: ReleaseStatus;
}

export class ReleaseConflictError extends Error {
  detail: string | null;

  constructor(detail?: string) {
    super(
      "This release changed since you loaded it, so the action was rejected as a conflict. Reload the releases list and try again.",
    );
    this.name = "ReleaseConflictError";
    this.detail = detail ?? null;
  }
}

async function readErrorMessage(res: Response): Promise<string> {
  const raw = await res.text();
  if (!raw) return "";
  try {
    const parsed = JSON.parse(raw) as { error?: unknown };
    if (typeof parsed?.error === "string") return parsed.error;
  } catch {
    // Not JSON — fall through to the raw body.
  }
  return raw;
}

async function postAdminFunction<T>(
  name: string,
  body: unknown,
  fallbackError: string,
): Promise<T> {
  const res = await fetch(`${functionsBaseUrl()}/${name}`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify(body ?? {}),
  });

  if (res.status === 403) {
    throw new AdminForbiddenError();
  }

  if (res.status === 409) {
    throw new ReleaseConflictError(await readErrorMessage(res));
  }

  if (!res.ok) {
    const message = await readErrorMessage(res);
    throw new Error(message || `${fallbackError} (${res.status})`);
  }

  return (await res.json()) as T;
}

export async function fetchReleases(): Promise<AppRelease[]> {
  const data = await postAdminFunction<AdminListReleasesResponse>(
    "admin-list-releases",
    {},
    "Failed to load releases",
  );
  return data.releases;
}

export async function saveReleaseDraft(
  draft: ReleaseDraft,
  id?: string,
): Promise<AdminReleaseMutationResponse> {
  return postAdminFunction<AdminReleaseMutationResponse>(
    "admin-save-release",
    id ? { id, ...draft } : draft,
    "Failed to save the release",
  );
}

export async function publishRelease(
  id: string,
): Promise<AdminReleaseMutationResponse> {
  return postAdminFunction<AdminReleaseMutationResponse>(
    "admin-publish-release",
    { release_id: id },
    "Failed to publish the release",
  );
}

export async function withdrawRelease(
  id: string,
): Promise<AdminReleaseMutationResponse> {
  return postAdminFunction<AdminReleaseMutationResponse>(
    "admin-withdraw-release",
    { release_id: id },
    "Failed to withdraw the release",
  );
}

export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? String(Math.round(value)) : value.toFixed(1);
  return `${rounded} ${units[unit]}`;
}

export function checksumPrefix(checksum: string | null, length = 10): string {
  if (!checksum) return "—";
  return checksum.slice(0, length);
}

export function installerHost(url: string | null): string {
  if (!url) return "—";
  try {
    return new URL(url).hostname;
  } catch {
    return "—";
  }
}
