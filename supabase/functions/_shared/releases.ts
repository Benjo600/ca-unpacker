export type ReleaseStatus = "draft" | "published" | "withdrawn";

export interface ReleaseRecord {
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
  created_by: string;
  created_at: string;
  published_by: string | null;
  published_at: string | null;
  withdrawn_by: string | null;
  withdrawn_at: string | null;
}

export interface ReleaseDraftInput {
  version: string;
  title: string;
  release_notes: string;
  installer_url: string;
  installer_sha256: string;
  installer_size: number;
  mandatory: boolean;
  minimum_supported_version: string | null;
}

export const APPROVED_HOSTS = [
  "github.com",
  "objects.githubusercontent.com",
  "github-releases.githubusercontent.com",
];

const VERSION_RE = /^\d+\.\d+\.\d+$/;
const CHECKSUM_RE = /^[0-9a-f]{64}$/;
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseVersion(value: unknown): string {
  if (typeof value !== "string") throw new Error("Version must be a string");
  const cleaned = value.trim().replace(/^v/i, "");
  if (!VERSION_RE.test(cleaned)) {
    throw new Error("Version must look like 1.2.3");
  }
  return cleaned;
}

export function compareVersions(left: string, right: string): number {
  const a = parseVersion(left).split(".").map(Number);
  const b = parseVersion(right).split(".").map(Number);
  for (let i = 0; i < 3; i += 1) {
    if (a[i] !== b[i]) return a[i] > b[i] ? 1 : -1;
  }
  return 0;
}

export function normalizeChecksum(value: unknown): string {
  if (typeof value !== "string") throw new Error("Checksum must be a string");
  const cleaned = value.trim().toLowerCase();
  if (!CHECKSUM_RE.test(cleaned)) {
    throw new Error("Checksum must be 64 lowercase hex characters");
  }
  return cleaned;
}

export function isApprovedInstallerUrl(value: unknown): boolean {
  if (typeof value !== "string" || value.trim() === "") return false;
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    return false;
  }
  if (url.protocol !== "https:") return false;
  if (url.username || url.password) return false;
  if (url.port && url.port !== "443") return false;
  const host = url.hostname.toLowerCase();
  return APPROVED_HOSTS.some(
    (approved) => host === approved || host.endsWith(`.${approved}`),
  );
}

export function requirePositiveSize(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) {
    throw new Error("Installer size must be a positive whole number of bytes");
  }
  return value;
}

export function parseReleaseInput(
  body: Record<string, unknown>,
): ReleaseDraftInput {
  const allowed = [
    "id",
    "version",
    "title",
    "release_notes",
    "installer_url",
    "installer_sha256",
    "installer_size",
    "mandatory",
    "minimum_supported_version",
  ];
  for (const key of Object.keys(body)) {
    if (!allowed.includes(key)) throw new Error(`Unexpected field: ${key}`);
  }
  if (typeof body.title !== "string" || body.title.trim() === "") {
    throw new Error("Title is required");
  }
  if (!isApprovedInstallerUrl(body.installer_url)) {
    throw new Error("Installer URL must be HTTPS on an approved GitHub host");
  }
  if (typeof body.release_notes !== "undefined" && typeof body.release_notes !== "string") {
    throw new Error("Release notes must be text");
  }
  if (typeof body.mandatory !== "undefined" && typeof body.mandatory !== "boolean") {
    throw new Error("Mandatory must be true or false");
  }
  const minimum = body.minimum_supported_version;
  if (
    minimum !== undefined &&
    minimum !== null &&
    minimum !== "" &&
    typeof minimum !== "string"
  ) {
    throw new Error("Minimum supported version must be text");
  }
  return {
    version: parseVersion(body.version),
    title: body.title.trim(),
    release_notes: typeof body.release_notes === "string" ? body.release_notes : "",
    installer_url: String(body.installer_url).trim(),
    installer_sha256: normalizeChecksum(body.installer_sha256),
    installer_size: requirePositiveSize(body.installer_size),
    mandatory: body.mandatory === true,
    minimum_supported_version:
      typeof minimum === "string" && minimum.trim() !== ""
        ? parseVersion(minimum)
        : null,
  };
}

export function requireReleaseId(body: Record<string, unknown>): string {
  for (const key of Object.keys(body)) {
    if (key !== "release_id") throw new Error(`Unexpected field: ${key}`);
  }
  const id = body.release_id;
  if (typeof id !== "string" || !UUID_RE.test(id)) {
    throw new Error("release_id must be a valid id");
  }
  return id;
}

export function selectLatestRelease(
  currentVersion: string,
  release: ReleaseRecord | null,
): (ReleaseRecord & { mandatory: boolean }) | null {
  if (!release || release.status !== "published") return null;
  if (compareVersions(currentVersion, release.version) >= 0) return null;
  const minimum = release.minimum_supported_version;
  const belowMinimum = minimum
    ? compareVersions(currentVersion, minimum) < 0
    : false;
  return { ...release, mandatory: release.mandatory || belowMinimum };
}

export function publicRelease(release: ReleaseRecord) {
  return {
    version: release.version,
    title: release.title,
    release_notes: release.release_notes,
    installer_url: release.installer_url,
    installer_sha256: release.installer_sha256,
    installer_size: release.installer_size,
    mandatory: release.mandatory,
    published_at: release.published_at,
  };
}

export function isSupportedPlatform(platform: unknown): boolean {
  return platform === "windows";
}

export function isSupportedArch(arch: unknown): boolean {
  return arch === "x64" || arch === "arm64";
}
