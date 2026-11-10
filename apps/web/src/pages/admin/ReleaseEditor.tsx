import { FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ReleaseConflictError,
  fetchReleases,
  formatBytes,
  formatDateTime,
  saveReleaseDraft,
  publishRelease,
  type AppRelease,
  type ReleaseDraft,
} from "../../lib/admin";
import { ReleasePublishDialog, StatusBadge } from "./Releases";

const APPROVED_HOSTS = [
  "github.com",
  "objects.githubusercontent.com",
  "github-releases.githubusercontent.com",
];

const VERSION_RE = /^\d+\.\d+\.\d+$/;
const CHECKSUM_RE = /^[0-9a-f]{64}$/;
const SIZE_RE = /^\d+$/;

interface FormState {
  version: string;
  title: string;
  release_notes: string;
  installer_url: string;
  installer_sha256: string;
  installer_size: string;
  mandatory: boolean;
  minimum_supported_version: string;
}

type FieldErrors = Partial<Record<keyof FormState, string>>;

const EMPTY_FORM: FormState = {
  version: "",
  title: "",
  release_notes: "",
  installer_url: "",
  installer_sha256: "",
  installer_size: "",
  mandatory: false,
  minimum_supported_version: "",
};

function normalizeVersion(value: string): string {
  return value.trim().replace(/^v/i, "");
}

function normalizeChecksum(value: string): string {
  return value.trim().toLowerCase();
}

function isApprovedInstallerUrl(value: string): boolean {
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

function formFromRelease(release: AppRelease): FormState {
  return {
    version: release.version,
    title: release.title,
    release_notes: release.release_notes,
    installer_url: release.installer_url,
    installer_sha256: release.installer_sha256,
    installer_size: String(release.installer_size),
    mandatory: release.mandatory,
    minimum_supported_version: release.minimum_supported_version ?? "",
  };
}

function validate(form: FormState): FieldErrors {
  const errors: FieldErrors = {};

  if (!VERSION_RE.test(normalizeVersion(form.version))) {
    errors.version = "Use a strict major.minor.patch version, e.g. 1.4.2.";
  }
  if (form.title.trim() === "") {
    errors.title = "Title is required.";
  }
  if (!isApprovedInstallerUrl(form.installer_url)) {
    errors.installer_url =
      "Must be an HTTPS link on github.com, objects.githubusercontent.com or github-releases.githubusercontent.com.";
  }
  if (!CHECKSUM_RE.test(normalizeChecksum(form.installer_sha256))) {
    errors.installer_sha256 =
      "Must be 64 hex characters. Uppercase is converted to lowercase on save.";
  }
  const size = form.installer_size.trim();
  if (!SIZE_RE.test(size) || Number(size) <= 0) {
    errors.installer_size =
      "Enter the installer size in whole bytes, greater than zero.";
  }
  const minimum = normalizeVersion(form.minimum_supported_version);
  if (minimum !== "" && !VERSION_RE.test(minimum)) {
    errors.minimum_supported_version =
      "Leave this empty, or use major.minor.patch, e.g. 1.0.0.";
  }

  return errors;
}

function toDraft(form: FormState): ReleaseDraft {
  const minimum = normalizeVersion(form.minimum_supported_version);
  return {
    version: normalizeVersion(form.version),
    title: form.title.trim(),
    release_notes: form.release_notes,
    installer_url: form.installer_url.trim(),
    installer_sha256: normalizeChecksum(form.installer_sha256),
    installer_size: Number(form.installer_size.trim()),
    mandatory: form.mandatory,
    minimum_supported_version: minimum === "" ? null : minimum,
  };
}

function matchesStored(draft: ReleaseDraft, release: AppRelease): boolean {
  return (
    draft.version === release.version &&
    draft.title === release.title &&
    draft.release_notes === release.release_notes &&
    draft.installer_url === release.installer_url &&
    draft.installer_sha256 === release.installer_sha256 &&
    draft.installer_size === release.installer_size &&
    draft.mandatory === release.mandatory &&
    draft.minimum_supported_version === (release.minimum_supported_version ?? null)
  );
}

export default function ReleaseEditor() {
  const { id } = useParams<{ id: string }>();
  const isNew = !id;
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState<FormState>(() => {
    const state = location.state as
      | { prefill?: Partial<Pick<FormState, "release_notes">> }
      | null;
    const prefill = state?.prefill;
    if (!isNew || !prefill) return EMPTY_FORM;
    return { ...EMPTY_FORM, release_notes: prefill.release_notes ?? "" };
  });
  const [release, setRelease] = useState<AppRelease | null>(null);
  const [loading, setLoading] = useState(!isNew);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    if (!id) {
      setRelease(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    fetchReleases()
      .then((all) => {
        if (cancelled) return;
        const match = all.find((r) => r.id === id) ?? null;
        setRelease(match);
        if (match) setForm(formFromRelease(match));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load release");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  const readOnly = release !== null && release.status !== "draft";
  const errors = validate(form);
  const formValid = Object.keys(errors).length === 0;
  const dirty = release !== null && (!formValid || !matchesStored(toDraft(form), release));
  const canPublish = release !== null && release.status === "draft" && !dirty;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (readOnly) return;

    const found = validate(form);
    setFieldErrors(found);
    setError(null);

    if (Object.keys(found).length > 0) {
      setError("Fix the highlighted fields before saving.");
      return;
    }

    setSaving(true);

    try {
      const draft = toDraft(form);
      await saveReleaseDraft(draft, id);
      navigate("/admin/releases", {
        state: {
          message: `Draft v${draft.version} saved. Publish it from the releases list when you are ready.`,
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save the draft");
    } finally {
      setSaving(false);
    }
  }

  async function handlePublish() {
    if (!release) return;

    setPublishing(true);
    setPublishError(null);

    try {
      await publishRelease(release.id);
      navigate("/admin/releases", {
        state: { message: `v${release.version} is now published.` },
      });
    } catch (err) {
      setPublishError(
        err instanceof ReleaseConflictError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Failed to publish release",
      );
    } finally {
      setPublishing(false);
    }
  }

  if (loading) {
    return <p className="muted">Loading release…</p>;
  }

  if (!isNew && !release) {
    return (
      <div>
        <p className="error">
          {error ?? "Release not found."}
        </p>
        <Link to="/admin/releases">Back to releases</Link>
      </div>
    );
  }

  return (
    <div>
      <p className="muted">
        <Link to="/admin/releases">← Releases</Link>
      </p>

      <div className="page-head">
        <div>
          <h1>{isNew ? "New release" : `v${release?.version ?? ""}`}</h1>
          <p className="muted">
            {isNew
              ? "Draft a desktop build. Nothing reaches users until you publish it."
              : release?.title}
          </p>
        </div>
        {release && <StatusBadge status={release.status} />}
      </div>

      {error && <p className="error">{error}</p>}

      {readOnly && release && (
        <p className="read-only-note">
          {release.status === "published"
            ? "This release is published and read-only. Installed copies already depend on it, so its files cannot be changed — withdraw it from the releases list to stop offering it to future update checks."
            : `This release was withdrawn${
                release.withdrawn_at
                  ? ` on ${formatDateTime(release.withdrawn_at)}`
                  : ""
              } and is read-only. It cannot be published again; save a new draft instead.`}
        </p>
      )}

      <form
        className="docket docket-wide release-form"
        style={{ margin: "24px 0 0" }}
        onSubmit={handleSubmit}
      >
        <div className="form-grid">
          <div className="field">
            <label htmlFor="version">Version</label>
            <input
              id="version"
              value={form.version}
              onChange={(e) => update("version", e.target.value)}
              placeholder="1.4.2"
              autoComplete="off"
              spellCheck={false}
              disabled={readOnly}
            />
            {fieldErrors.version && (
              <p className="field-error">{fieldErrors.version}</p>
            )}
          </div>

          <div className="field">
            <label htmlFor="minimum">Minimum supported version (optional)</label>
            <input
              id="minimum"
              value={form.minimum_supported_version}
              onChange={(e) =>
                update("minimum_supported_version", e.target.value)
              }
              placeholder="1.0.0"
              autoComplete="off"
              spellCheck={false}
              disabled={readOnly}
            />
            {fieldErrors.minimum_supported_version && (
              <p className="field-error">
                {fieldErrors.minimum_supported_version}
              </p>
            )}
          </div>

          <div className="field span-2">
            <label htmlFor="title">Title</label>
            <input
              id="title"
              value={form.title}
              onChange={(e) => update("title", e.target.value)}
              placeholder="Faster bulk unpacking"
              disabled={readOnly}
            />
            {fieldErrors.title && (
              <p className="field-error">{fieldErrors.title}</p>
            )}
          </div>

          <div className="field span-2">
            <label htmlFor="notes">Release notes</label>
            <textarea
              id="notes"
              rows={5}
              value={form.release_notes}
              onChange={(e) => update("release_notes", e.target.value)}
              placeholder="What changed in this build?"
              disabled={readOnly}
            />
          </div>

          <div className="field span-2">
            <label htmlFor="installer_url">Installer URL</label>
            <input
              id="installer_url"
              value={form.installer_url}
              onChange={(e) => update("installer_url", e.target.value)}
              placeholder="https://github.com/org/repo/releases/download/v1.4.2/CA-Unpacker-Setup.exe"
              autoComplete="off"
              spellCheck={false}
              disabled={readOnly}
            />
            {fieldErrors.installer_url && (
              <p className="field-error">{fieldErrors.installer_url}</p>
            )}
          </div>

          <div className="field">
            <label htmlFor="checksum">SHA-256 checksum</label>
            <input
              id="checksum"
              className="mono"
              value={form.installer_sha256}
              onChange={(e) => update("installer_sha256", e.target.value)}
              placeholder="64 hex characters"
              autoComplete="off"
              spellCheck={false}
              disabled={readOnly}
            />
            {fieldErrors.installer_sha256 && (
              <p className="field-error">{fieldErrors.installer_sha256}</p>
            )}
          </div>

          <div className="field">
            <label htmlFor="size">Installer size (bytes)</label>
            <input
              id="size"
              value={form.installer_size}
              onChange={(e) => update("installer_size", e.target.value)}
              placeholder="48234496"
              inputMode="numeric"
              autoComplete="off"
              disabled={readOnly}
            />
            {fieldErrors.installer_size && (
              <p className="field-error">{fieldErrors.installer_size}</p>
            )}
            {form.installer_size.trim() !== "" &&
              SIZE_RE.test(form.installer_size.trim()) && (
                <p className="muted">
                  ≈ {formatBytes(Number(form.installer_size.trim()))}
                </p>
              )}
          </div>

          <div className="field span-2">
            <label className="checkbox-field" htmlFor="mandatory">
              <input
                id="mandatory"
                type="checkbox"
                checked={form.mandatory}
                onChange={(e) => update("mandatory", e.target.checked)}
                disabled={readOnly}
              />
              <span>
                Mandatory update — installed copies must upgrade before they can
                keep using the app.
              </span>
            </label>
          </div>
        </div>

        <div className="actions-row">
          {!readOnly && (
            <button type="submit" className="btn btn-ink" disabled={saving}>
              {saving ? "Saving…" : "Save draft"}
            </button>
          )}
          {canPublish && (
            <button
              type="button"
              className="btn btn-tab"
              onClick={() => {
                setPublishError(null);
                setConfirming(true);
              }}
            >
              Publish…
            </button>
          )}
          <Link to="/admin/releases" className="btn btn-plain">
            {readOnly ? "Back to releases" : "Cancel"}
          </Link>
        </div>

        {release?.status === "draft" && dirty && (
          <p className="muted" style={{ marginTop: 12 }}>
            Save your changes before publishing — publishing sends the stored
            draft exactly as it was last saved.
          </p>
        )}
      </form>

      {confirming && release && (
        <ReleasePublishDialog
          release={release}
          busy={publishing}
          error={publishError}
          onCancel={() => {
            setConfirming(false);
            setPublishError(null);
          }}
          onConfirm={handlePublish}
        />
      )}
    </div>
  );
}
