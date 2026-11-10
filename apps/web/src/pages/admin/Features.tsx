import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchReleases,
  formatBytes,
} from "../../lib/admin";
import {
  GitHubBranch,
  GitHubBuild,
  GitHubCommit,
  KIND_LABELS,
  buildLooksComplete,
  commitUrl,
  commitsToReleaseNotes,
  fetchBranches,
  fetchCiBuilds,
  fetchRecentCommits,
  formatCommitDate,
  shortSha,
} from "../../lib/github";

const KIND_BADGE: Record<string, string> = {
  feature: "badge badge-pro",
  fix: "badge badge-starter",
  small: "badge badge-draft",
};

const KIND_ORDER: Array<"feature" | "fix" | "small"> = [
  "feature",
  "fix",
  "small",
];

function CommitRow({ commit }: { commit: GitHubCommit }) {
  return (
    <tr key={commit.sha}>
      <td>
        {commit.isMerge ? (
          <span className="badge badge-draft" style={{ marginRight: 8 }}>
            merge
          </span>
        ) : null}
        <span className={KIND_BADGE[commit.kind]} style={{ marginRight: 8 }}>
          {KIND_LABELS[commit.kind]}
        </span>
        {commit.message || "(no message)"}
      </td>
      <td>{commit.author}</td>
      <td>{formatCommitDate(commit.date)}</td>
      <td className="mono">
        <a href={commitUrl(commit.sha)} target="_blank" rel="noreferrer">
          {shortSha(commit.sha)}
        </a>
      </td>
    </tr>
  );
}

export default function Features() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [commits, setCommits] = useState<GitHubCommit[] | null>(null);
  const [branches, setBranches] = useState<GitHubBranch[] | null>(null);
  const [builds, setBuilds] = useState<GitHubBuild[] | null>(null);
  const [lastPublishedAt, setLastPublishedAt] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const releases = await fetchReleases();
        const published = releases
          .filter((r) => r.status === "published" && r.published_at)
          .map((r) => r.published_at as string)
          .sort();
        if (cancelled) return;
        setLastPublishedAt(published.pop() ?? null);

        fetchBranches()
          .then((data) => {
            if (!cancelled) setBranches(data);
          })
          .catch(() => {
            if (!cancelled) setBranches([]);
          });

        fetchCiBuilds()
          .then((data) => {
            if (!cancelled) setBuilds(data);
          })
          .catch(() => {
            if (!cancelled) setBuilds([]);
          });

        const data = await fetchRecentCommits(lastPublishedAt ?? null);
        if (!cancelled) setCommits(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load GitHub activity");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const byKind = useMemo(() => {
    const grouped: Record<"feature" | "fix" | "small", GitHubCommit[]> = {
      feature: [],
      fix: [],
      small: [],
    };
    for (const commit of commits ?? []) {
      grouped[commit.kind].push(commit);
    }
    return grouped;
  }, [commits]);

  async function handleCopyNotes() {
    if (!commits || commits.length === 0) return;
    try {
      await navigator.clipboard.writeText(commitsToReleaseNotes(commits));
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
    setTimeout(() => setCopyState("idle"), 2000);
  }

  function handleDraftFromBuild(build: GitHubBuild) {
    if (!commits) return;
    navigate("/admin/releases/new", {
      state: {
        prefill: {
          version: build.version,
          title: `v${build.version} update`,
          release_notes: commitsToReleaseNotes(commits),
          installer_url: build.url,
          installer_sha256: build.sha256,
          installer_size: String(build.size),
        },
      },
    });
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>New features</h1>
          <p className="muted">
            Everything pushed to GitHub since{" "}
            {lastPublishedAt
              ? "the last published release"
              : "your last published release (none yet)"}
            , sorted by kind. Commits tagged <code>feat:</code> are new
            features, <code>fix:</code> update existing features, everything
            else is a small update.
          </p>
        </div>
        {commits && commits.length > 0 && (
          <div className="row-actions">
            <button
              type="button"
              className="btn btn-tab btn-small"
              onClick={handleCopyNotes}
            >
              {copyState === "copied"
                ? "Copied!"
                : copyState === "failed"
                  ? "Copy failed"
                  : "Copy release notes"}
            </button>
            <Link
              to="/admin/releases/new"
              state={{ prefill: { release_notes: commitsToReleaseNotes(commits) } }}
              className="btn btn-ink btn-small"
            >
              Start release draft
            </Link>
          </div>
        )}
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading GitHub activity…</p>}

      {/* CI auto-builds waiting for your go/no-go */}
      {Array.isArray(builds) && builds.length > 0 && (
        <section className="docket docket-wide" style={{ margin: "24px 0", padding: 24 }}>
          <div className="page-head" style={{ marginBottom: 12 }}>
            <div>
              <h2 style={{ margin: 0 }}>Auto-built installers ready to test</h2>
              <p className="muted">
                GitHub Actions built these on every push. Install one on a
                machine, try it, then turn it into a release draft here.
              </p>
            </div>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Build</th>
                <th>Built</th>
                <th>Size</th>
                <th className="mono">SHA-256</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {builds.map((build) => (
                <tr key={build.tagName}>
                  <td>
                    <a
                      href={build.htmlUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {build.tagName}
                    </a>
                    {build.isPrerelease && (
                      <span className="badge badge-draft" style={{ marginLeft: 8 }}>
                        CI build
                      </span>
                    )}
                  </td>
                  <td>{formatCommitDate(build.createdAt)}</td>
                  <td>{formatBytes(build.size)}</td>
                  <td className="mono">{build.sha256.slice(0, 12)}…</td>
                  <td>
                    {buildLooksComplete(build) && (
                      <button
                        type="button"
                        className="btn btn-ink btn-small"
                        onClick={() => handleDraftFromBuild(build)}
                      >
                        Create release draft
                      </button>
                    )}
                    {!buildLooksComplete(build) && (
                      <span className="muted">Incomplete — skip</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Pushes by kind */}
      {KIND_ORDER.map((kind) => (
        <section
          key={kind}
          className="docket docket-wide"
          style={{ margin: "24px 0", padding: 24 }}
        >
          <div className="page-head" style={{ marginBottom: 12 }}>
            <div>
              <h2 style={{ margin: 0 }}>
                <span className={KIND_BADGE[kind]} style={{ marginRight: 8 }}>
                  {KIND_LABELS[kind]}
                </span>
              </h2>
              <p className="muted">
                {byKind[kind].length} commit
                {byKind[kind].length === 1 ? "" : "s"}
              </p>
            </div>
          </div>
          {byKind[kind].length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>
              Nothing in this bucket.
            </p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Commit</th>
                  <th>Author</th>
                  <th>Pushed</th>
                  <th className="mono">SHA</th>
                </tr>
              </thead>
              <tbody>
                {byKind[kind].map((commit) => (
                  <CommitRow key={commit.sha} commit={commit} />
                ))}
              </tbody>
            </table>
          )}
        </section>
      ))}

      {/* Branch activity */}
      {branches && branches.length > 0 && (
        <section
          className="docket docket-wide"
          style={{ margin: "24px 0 0", padding: 24 }}
        >
          <div className="page-head" style={{ marginBottom: 12 }}>
            <div>
              <h2 style={{ margin: 0 }}>Branches working on</h2>
              <p className="muted">
                feat/* branches are new work in progress, fix/* branches patch
                existing features.
              </p>
            </div>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Branch</th>
                <th>Kind</th>
                <th className="mono">Last commit</th>
              </tr>
            </thead>
            <tbody>
              {branches.map((branch) => (
                <tr key={branch.name}>
                  <td>{branch.name}</td>
                  <td>
                    <span className={KIND_BADGE[branch.kind]}>
                      {KIND_LABELS[branch.kind]}
                    </span>
                  </td>
                  <td className="mono">
                    <a href={commitUrl(branch.sha)} target="_blank" rel="noreferrer">
                      {shortSha(branch.sha)}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
