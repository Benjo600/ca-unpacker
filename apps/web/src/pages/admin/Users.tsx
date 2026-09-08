import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchAdminOrgs,
  formatDate,
  formatFileLimit,
  updateOrgPlan,
  type AdminOrg,
  type PlanType,
} from "../../lib/admin";

function PlanBadge({ plan }: { plan: PlanType }) {
  return <span className={`badge badge-${plan}`}>{plan}</span>;
}

export default function Users() {
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchAdminOrgs()
      .then(setOrgs)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  async function handlePlanChange(orgId: string, plan: PlanType) {
    setUpdatingId(orgId);
    setError(null);
    try {
      await updateOrgPlan(orgId, plan);
      setOrgs((prev) =>
        prev.map((o) =>
          o.id === orgId
            ? {
                ...o,
                plan,
                file_limit: plan === "pro" ? null : plan === "starter" ? 100 : 0,
              }
            : o,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update plan");
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleSuspend(orgId: string, e: React.MouseEvent) {
    e.stopPropagation();
    await handlePlanChange(orgId, "suspended");
  }

  if (loading) {
    return <p className="muted">Loading users…</p>;
  }

  return (
    <div>
      <h1>Users</h1>
      <p className="muted">All registered CA firms. Click a row for detail.</p>
      {error && <p className="error">{error}</p>}
      <div className="docket docket-wide" style={{ margin: "24px 0 0", padding: 0 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Firm</th>
              <th>Plan</th>
              <th>Files</th>
              <th>Last active</th>
              <th>Devices</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {orgs.map((org) => (
              <tr
                key={org.id}
                className="row-link"
                onClick={() => navigate(`/admin/users/${org.id}`)}
              >
                <td>{org.email || "—"}</td>
                <td>{org.name}</td>
                <td>
                  <PlanBadge plan={org.plan} />
                </td>
                <td>
                  {org.files_used} / {formatFileLimit(org.file_limit)}
                </td>
                <td>{formatDate(org.last_active_at)}</td>
                <td>{org.device_count}</td>
                <td>{formatDate(org.created_at)}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <select
                    className="plan-select"
                    value={org.plan}
                    disabled={updatingId === org.id}
                    onChange={(e) =>
                      handlePlanChange(org.id, e.target.value as PlanType)
                    }
                  >
                    <option value="starter">starter</option>
                    <option value="pro">pro</option>
                    <option value="suspended">suspended</option>
                  </select>
                  {org.plan !== "suspended" && (
                    <button
                      type="button"
                      className="btn btn-ink"
                      style={{ marginLeft: 8, padding: "6px 10px", fontSize: 12 }}
                      disabled={updatingId === org.id}
                      onClick={(e) => handleSuspend(org.id, e)}
                    >
                      Suspend
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {orgs.length === 0 && (
          <p className="muted" style={{ padding: 20 }}>
            No organizations yet.
          </p>
        )}
      </div>
    </div>
  );
}
