// Reads commit activity from the public GitHub API — no token needed for a
// public repo. This is what makes pushed features visible to the operator
// before a release is built and published.

const REPO_OWNER = "Benjo600";
const REPO_NAME = "ca-unpacker";
const DEFAULT_LIMIT = 30;

export interface GitHubCommit {
  sha: string;
  message: string;
  author: string;
  date: string;
  isMerge: boolean;
  kind: CommitKind;
}

export type CommitKind = "feature" | "fix" | "small";

export const KIND_LABELS: Record<CommitKind, string> = {
  feature: "New feature",
  fix: "Existing feature update",
  small: "Small update",
};

/**
 * Pushes are "tagged" by their conventional-commit prefix in the subject:
 *   feat: / feat(scope)   -> New feature
 *   fix:  / fix(scope)    -> Existing feature update
 *   anything else         -> Small update (the popup with Install now / Later)
 */
export function classifyCommit(message: string): CommitKind {
  const subject = parseMessage(message);
  if (/^feat(\([^)]*\))?[!:]/i.test(subject)) return "feature";
  if (/^fix(\([^)]*\))?[!:]/i.test(subject)) return "fix";
  return "small";
}

export interface GitHubBranch {
  name: string;
  sha: string;
  kind: "feature" | "fix" | "small";
}

export interface GitHubBuild {
  tagName: string;
  version: string;
  url: string;
  htmlUrl: string;
  size: number;
  sha256: string;
  createdAt: string;
  isPrerelease: boolean;
}


function parseMessage(raw: string): string {
  return String(raw ?? "")
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length > 0) ?? "";
}

function classifyBranchName(name: string): "feature" | "fix" | "small" {
  if (/^feat\//i.test(name)) return "feature";
  if (/^fix\//i.test(name)) return "fix";
  return "small";
}

function sanitiseAuthor(commit: {
  author?: { login?: string | null } | null;
  commit: { author?: { name?: string | null } | null };
}): string {
  if (commit.author?.login) return commit.author.login;
  if (commit.commit.author?.name) return commit.commit.author.name;
  return "unknown";
}

export async function fetchRecentCommits(
  sinceISO: string | null = null,
  limit: number = DEFAULT_LIMIT,
): Promise<GitHubCommit[]> {
  const url = new URL(
    `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/commits`,
  );
  url.searchParams.set("sha", "main");
  url.searchParams.set("per_page", String(Math.min(Math.max(limit, 1), 100)));
  if (sinceISO) url.searchParams.set("since", sinceISO);

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      headers: { Accept: "application/vnd.github+json" },
    });
  } catch {
    throw new Error("Could not reach GitHub. Check your connection.");
  }

  if (res.status === 403 || res.status === 429) {
    throw new Error(
      "GitHub is rate-limiting this browser right now. Try again in a few minutes.",
    );
  }
  if (res.status === 404) {
    throw new Error("GitHub repository not found.");
  }
  if (!res.ok) {
    throw new Error(`GitHub returned ${res.status}.`);
  }

  const data: unknown = await res.json();
  if (!Array.isArray(data)) {
    throw new Error("Unexpected response from GitHub.");
  }

  return data.map((entry) => {
    const commit = (entry as { commit?: unknown }).commit as
      | {
          message?: string;
          author?: { date?: string | null } | null;
        }
      | undefined;
    const sha = String((entry as { sha?: unknown }).sha ?? "");
    const parents = (entry as { parents?: unknown[] }).parents;
    const subject = parseMessage(commit?.message ?? "");

    return {
      sha,
      message: subject,
      author: sanitiseAuthor(entry as never),
      date: String(commit?.author?.date ?? ""),
      isMerge: Array.isArray(parents) && parents.length > 1,
      kind: classifyCommit(subject),
    } satisfies GitHubCommit;
  });
}

export async function fetchBranches(limit = 30): Promise<GitHubBranch[]> {
  let res: Response;
  try {
    res = await fetch(
      `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/branches?per_page=100`,
      { headers: { Accept: "application/vnd.github+json" } },
    );
  } catch {
    throw new Error("Could not reach GitHub. Check your connection.");
  }
  if (!res.ok) throw new Error(`GitHub returned ${res.status}.`);

  const data: unknown = await res.json();
  if (!Array.isArray(data)) throw new Error("Unexpected response from GitHub.");

  return data
    .map((entry) => {
      const name = String((entry as { name?: unknown }).name ?? "");
      const commit = (entry as { commit?: { sha?: unknown } }).commit;
      return {
        name,
        sha: String(commit?.sha ?? ""),
        kind: classifyBranchName(name),
      } satisfies GitHubBranch;
    })
    .filter((b) => b.name.toLowerCase() !== "main")
    .slice(0, limit);
}

/**
 * Public repo: prereleases land here from the CI builder. The workflow writes
 * the exact size and SHA-256 into the release body so the dashboard can prefill
 * a Supabase draft without ever holding a repo token.
 */
export async function fetchCiBuilds(limit = 5): Promise<GitHubBuild[]> {
  let res: Response;
  try {
    res = await fetch(
      `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases?per_page=20`,
      { headers: { Accept: "application/vnd.github+json" } },
    );
  } catch {
    throw new Error("Could not reach GitHub. Check your connection.");
  }
  if (!res.ok) throw new Error(`GitHub returned ${res.status}.`);

  const data: unknown = await res.json();
  if (!Array.isArray(data)) throw new Error("Unexpected response from GitHub.");

  const builds: GitHubBuild[] = [];
  for (const entry of data) {
    const release = entry as {
      tag_name?: unknown;
      prerelease?: unknown;
      draft?: unknown;
      html_url?: unknown;
      body?: unknown;
      created_at?: unknown;
      assets?: Array<{ browser_download_url?: unknown; size?: unknown }>;
    };
    if (release.draft) continue;
    // Only CI auto-builds are actionable here; hand-published stable
    // releases have no sha/size lines and never reach users' apps.
    if (!release.prerelease) continue;

    const tagName = String(release.tag_name ?? "");
    if (!/^v\d+\.\d+\.\d+$/.test(tagName)) continue;

    const asset = release.assets?.[0];
    const body = String(release.body ?? "");
    const shaMatch = body.match(/sha256:\s*([0-9a-f]{64})/i);
    const sizeMatch = body.match(/size:\s*(\d+)/i);

    builds.push({
      tagName,
      version: tagName.slice(1),
      url: String(asset?.browser_download_url ?? ""),
      htmlUrl: String(release.html_url ?? ""),
      size: asset?.size ? Number(asset.size) : sizeMatch ? Number(sizeMatch[1]) : 0,
      sha256: shaMatch ? shaMatch[1].toLowerCase() : "",
      createdAt: String(release.created_at ?? ""),
      isPrerelease: Boolean(release.prerelease),
    });
    if (builds.length >= limit) break;
  }
  return builds;
}

export function buildLooksComplete(build: GitHubBuild): boolean {
  return (
    Boolean(build.url) &&
    /^[0-9a-f]{64}$/.test(build.sha256) &&
    build.size > 0
  );
}

export function formatCommitDate(iso: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortSha(sha: string, length = 7): string {
  return sha ? sha.slice(0, length) : "—";
}

export function commitUrl(sha: string): string {
  return `https://github.com/${REPO_OWNER}/${REPO_NAME}/commit/${sha}`;
}

/** Draft release notes: one bullet per commit, merges labelled. */
export function commitsToReleaseNotes(commits: GitHubCommit[]): string {
  return commits
    .filter((commit) => commit.message)
    .map((commit) => `- ${commit.message}${commit.isMerge ? " (merge)" : ""}`)
    .join("\n");
}
