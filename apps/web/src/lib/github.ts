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
}

function parseMessage(raw: string): string {
  return String(raw ?? "")
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length > 0) ?? "";
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

    return {
      sha,
      message: parseMessage(commit?.message ?? ""),
      author: sanitiseAuthor(entry as never),
      date: String(commit?.author?.date ?? ""),
      isMerge: Array.isArray(parents) && parents.length > 1,
    } satisfies GitHubCommit;
  });
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
