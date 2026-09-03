import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  currentMonthLabel,
  fetchAdminOrgs,
  formatDate,
  formatFileLimit,
  updateOrgPlan,
  type AdminOrg,
  type PlanType,
} from "../../lib/admin";

export default function UserDetail() {
  const { id } = useParams<{ id: string }>();
  const [org, setOrg] = useState<AdminOrg | null>(null);
  const [plan, setPlan] = useState<PlanType>("starter");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchAdminOrgs()
      .then((orgs) => {
        const match = orgs.find((o) => o.id === id) ?? null;
        setOrg(match);
        if (match) setPlan(match.plan);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [id]);

  async function handlePlanSubmit(e: FormEvent) {
    e.preventDefault();
    if (!org) return;

    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      await updateOrgPlan(org.id, plan);
      setOrg((prev) =>
        prev
          ? {
              ...prev,
              plan,
              file_limit:
                plan === "pro" ? null : plan === "starter" ? 100 : 0,
            }
          : prev,
      );
      setMessage("Plan updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update plan");
    } finally {
      setSaving(false);
    }
  }

  async function toggleSuspend() {
    if (!org) return;
    const nextPlan: PlanType = org.plan === "suspended" ? "starter" : "suspended";
    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      await updateOrgPlan(org.id, nextPlan);
      setPlan(nextPlan);
      setOrg((prev) =>
        prev
          ? {
              ...prev,
              plan: nextPlan,
              file_limit: nextPlan === "starter" ? 100 : 0,
            }
          : prev,
      );
      setMessage(nextPlan === "suspended" ? "Account suspended." : "Account restored to starter.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="muted">Loading user…</p>;
  }

  if (!org) {
    return (
      <div>
        <p className="error">Organization not found.</p>
        <Link to="/admin/users">Back to users</Link>
      </div>
    );
  }

  const month = currentMonthLabel();

  return (
    <div>
      <p className="muted">
        <Link to="/admin/users">← Users</Link>
      </p>
      <h1>{org.name}</h1>
      <p className="muted">{org.email}</p>
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      <div className="detail-grid" style={{ marginTop: 32 }}>
        <section className="detail-section docket">
          <h3>Usage</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Month</th>
                <th>Files processed</th>
                <th>Limit</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{month}</td>
                <td>{org.files_used}</td>
                <td>{formatFileLimit(org.file_limit)}</td>
              </tr>
            </tbody>
          </table>
          <p className="muted" style={{ marginTop: 12 }}>
            Historical months will appear here once the admin API exposes usage
            history.
          </p>
        </section>

        <section className="detail-section docket">
          <h3>Devices</h3>
          <p>
            <strong>{org.device_count}</strong> registered device
            {org.device_count === 1 ? "" : "s"}
          </p>
          <p className="muted">
            Per-device labels and last-seen timestamps require a future admin API
            extension.
          </p>
        </section>

        <section className="detail-section docket">
          <h3>Account</h3>
          <p>
            Plan: <strong>{org.plan}</strong>
          </p>
          <p className="muted">Created {formatDate(org.created_at)}</p>
          <p className="muted">Last active {formatDate(org.last_active_at)}</p>

          <form onSubmit={handlePlanSubmit} style={{ marginTop: 16 }}>
            <div className="field">
              <label htmlFor="plan">Change plan</label>
              <select
                id="plan"
                value={plan}
                onChange={(e) => setPlan(e.target.value as PlanType)}
              >
                <option value="starter">starter</option>
                <option value="pro">pro</option>
                <option value="suspended">suspended</option>
              </select>
            </div>
            <div className="actions-row">
              <button type="submit" className="btn btn-ink" disabled={saving}>
                {saving ? "Saving…" : "Save plan"}
              </button>
              <button
                type="button"
                className="btn btn-tab"
                disabled={saving}
                onClick={toggleSuspend}
              >
                {org.plan === "suspended" ? "Unsuspend" : "Suspend account"}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
