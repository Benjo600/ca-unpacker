import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ReleaseConflictError,
  checksumPrefix,
  fetchReleases,
  formatBytes,
  formatDateTime,
  installerHost,
  publishRelease,
  withdrawRelease,
  type AppRelease,
  type ReleaseStatus,
} from "../../lib/admin";

export function StatusBadge({ status }: { status: ReleaseStatus }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function ReleasePublishDialog({
  release,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  release: AppRelease;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);

  return (
    <Modal
      title="Publish release"
      onClose={() => {
        if (!busy) onCancel();
      }}
    >
      <p className="muted">
        Every CA Unpacker install that checks for updates will be offered
        version <strong>{release.version}</strong>.
      </p>
      <dl className="confirm-list">
        <div>
          <dt>Version</dt>
          <dd>{release.version}</dd>
        </div>
        <div>
          <dt>Update type</dt>
          <dd>{release.mandatory ? "Mandatory" : "Optional"}</dd>
        </div>
        <div>
          <dt>Download host</dt>
          <dd>{installerHost(release.installer_url)}</dd>
        </div>
        <div>
          <dt>SHA-256</dt>
          <dd className="mono">{checksumPrefix(release.installer_sha256)}…</dd>
        </div>
      </dl>
      <p className="confirm-warning">Publish to all users</p>
      {error && <p className="error">{error}</p>}
      <label className="checkbox-field" htmlFor="publish-ack">
        <input
          id="publish-ack"
          type="checkbox"
          checked={acknowledged}
          disabled={busy}
          onChange={(e) => setAcknowledged(e.target.checked)}
        />
        <span>
          I have checked the version, download host and checksum above, and I
          understand this cannot be edited afterwards.
        </span>
      </label>
      <div className="actions-row">
        <button
          type="button"
          className="btn btn-ink"
          disabled={!acknowledged || busy}
          onClick={onConfirm}
        >
          {busy ? "Publishing…" : "Publish release"}
        </button>
        <button
          type="button"
          className="btn btn-plain"
          disabled={busy}
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </Modal>
  );
}

export default function Releases() {
  const [releases, setReleases] = useState<AppRelease[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [publishTarget, setPublishTarget] = useState<AppRelease | null>(null);
  const [withdrawTarget, setWithdrawTarget] = useState<AppRelease | null>(null);
  const [busy, setBusy] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const data = await fetchReleases();
      setReleases(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load releases");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const state = location.state as { message?: string } | null;
    if (state?.message) {
      setMessage(state.message);
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location, navigate]);

  async function handlePublish() {
    if (!publishTarget) return;
    setBusy(true);
    setActionError(null);

    try {
      await publishRelease(publishTarget.id);
      const publishedAt = new Date().toISOString();
      setReleases((prev) =>
        prev.map((r) =>
          r.id === publishTarget.id
            ? { ...r, status: "published", published_at: publishedAt }
            : r,
        ),
      );
      setMessage(`v${publishTarget.version} is now published.`);
      setPublishTarget(null);
    } catch (err) {
      if (err instanceof ReleaseConflictError) {
        setActionError(err.message);
        setPublishTarget(null);
        await load();
      } else {
        setActionError(err instanceof Error ? err.message : "Failed to publish release");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleWithdraw() {
    if (!withdrawTarget) return;
    setBusy(true);
    setActionError(null);

    try {
      await withdrawRelease(withdrawTarget.id);
      const withdrawnAt = new Date().toISOString();
      setReleases((prev) =>
        prev.map((r) =>
          r.id === withdrawTarget.id
            ? { ...r, status: "withdrawn", withdrawn_at: withdrawnAt }
            : r,
        ),
      );
      setMessage(`v${withdrawTarget.version} is withdrawn.`);
      setWithdrawTarget(null);
    } catch (err) {
      if (err instanceof ReleaseConflictError) {
        setActionError(err.message);
        setWithdrawTarget(null);
        await load();
      } else {
        setActionError(err instanceof Error ? err.message : "Failed to withdraw release");
      }
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="muted">Loading releases…</p>;
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Releases</h1>
          <p className="muted">
            Desktop builds offered to installed copies by the update check.
          </p>
        </div>
        <Link to="/admin/releases/new" className="btn btn-ink">
          New release
        </Link>
      </div>

      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}
      {actionError && <p className="error">{actionError}</p>}

      <div className="docket docket-wide" style={{ margin: "24px 0 0", padding: 0 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Status</th>
              <th>Update</th>
              <th>Creator</th>
              <th>Published</th>
              <th>Checksum</th>
              <th>Size</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {releases.map((release) => (
              <tr key={release.id}>
                <td>{release.version}</td>
                <td>
                  <StatusBadge status={release.status} />
                </td>
                <td>{release.mandatory ? "Mandatory" : "Optional"}</td>
                <td>{release.created_by || "—"}</td>
                <td>{formatDateTime(release.published_at)}</td>
                <td className="mono">{checksumPrefix(release.installer_sha256)}</td>
                <td>{formatBytes(release.installer_size)}</td>
                <td>
                  <div className="row-actions">
                    {release.status === "draft" && (
                      <>
                        <Link
                          to={`/admin/releases/${release.id}`}
                          className="btn btn-tab btn-small"
                        >
                          Edit
                        </Link>
                        <button
                          type="button"
                          className="btn btn-ink btn-small"
                          onClick={() => {
                            setActionError(null);
                            setMessage(null);
                            setPublishTarget(release);
                          }}
                        >
                          Publish
                        </button>
                      </>
                    )}
                    {release.status === "published" && (
                      <button
                        type="button"
                        className="btn btn-ink btn-small"
                        onClick={() => {
                          setActionError(null);
                          setMessage(null);
                          setWithdrawTarget(release);
                        }}
                      >
                        Withdraw
                      </button>
                    )}
                    {release.status === "withdrawn" && (
                      <span className="muted">Read-only</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {releases.length === 0 && (
          <p className="muted" style={{ padding: 20 }}>
            No releases yet. Create the first draft to get started.
          </p>
        )}
      </div>

      {publishTarget && (
        <ReleasePublishDialog
          release={publishTarget}
          busy={busy}
          error={actionError}
          onCancel={() => {
            setPublishTarget(null);
            setActionError(null);
          }}
          onConfirm={handlePublish}
        />
      )}

      {withdrawTarget && (
        <Modal
          title="Withdraw release"
          onClose={() => {
            if (!busy) {
              setWithdrawTarget(null);
              setActionError(null);
            }
          }}
        >
          <p>
            Withdrawing <strong>v{withdrawTarget.version}</strong> stops future
            update checks from seeing it.
          </p>
          <p className="muted">
            Copies that already installed this version are unaffected — nothing
            is uninstalled or downgraded. A withdrawn release cannot be
            published again; save a new draft instead.
          </p>
          {actionError && <p className="error">{actionError}</p>}
          <div className="actions-row">
            <button
              type="button"
              className="btn btn-ink"
              disabled={busy}
              onClick={handleWithdraw}
            >
              {busy ? "Withdrawing…" : "Withdraw release"}
            </button>
            <button
              type="button"
              className="btn btn-plain"
              disabled={busy}
              onClick={() => {
                setWithdrawTarget(null);
                setActionError(null);
              }}
            >
              Cancel
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
