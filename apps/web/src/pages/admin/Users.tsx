import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import PlanBadge from "../../components/PlanBadge";
import {
  fetchAdminOrgs,
  formatDate,
  formatFileLimit,
  updateOrgPlan,
  type AdminOrg,
  type PlanType,
} from "../../lib/admin";

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

  if (loading) {
    return <div className="h-64 animate-pulse rounded-xl bg-rule/40" />;
  }

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-accent">
          Accounts
        </p>
        <h1 className="font-display mt-2 text-4xl tracking-tight text-ink">
          Firms
        </h1>
        <p className="mt-2 text-sm text-mute">
          Click a row for details. Change plan from the dropdown.
        </p>
      </header>

      {error ? (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-bad">
          {error}
        </p>
      ) : null}

      <div className="overflow-hidden rounded-xl border border-rule/80 bg-white shadow-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead>
              <tr className="border-b border-rule bg-paper-bright text-[10px] font-bold uppercase tracking-wider text-mute">
                <th className="px-5 py-3.5">Firm</th>
                <th className="px-5 py-3.5">Email</th>
                <th className="px-5 py-3.5">Plan</th>
                <th className="px-5 py-3.5">Usage</th>
                <th className="px-5 py-3.5">Last active</th>
                <th className="px-5 py-3.5">Devices</th>
                <th className="px-5 py-3.5">Plan control</th>
                <th className="px-5 py-3.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-rule/80">
              {orgs.map((org) => (
                <tr
                  key={org.id}
                  onClick={() => navigate(`/admin/users/${org.id}`)}
                  className="group cursor-pointer transition hover:bg-paper-bright/80"
                >
                  <td className="px-5 py-4 font-semibold text-ink">{org.name}</td>
                  <td className="px-5 py-4 text-mute">{org.email || "—"}</td>
                  <td className="px-5 py-4">
                    <PlanBadge plan={org.plan} />
                  </td>
                  <td className="tabular-nums px-5 py-4 text-mute">
                    {org.files_used} / {formatFileLimit(org.file_limit)}
                  </td>
                  <td className="px-5 py-4 text-mute">
                    {formatDate(org.last_active_at)}
                  </td>
                  <td className="tabular-nums px-5 py-4 text-mute">
                    {org.device_count}
                  </td>
                  <td
                    className="px-5 py-4"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <select
                      value={org.plan}
                      disabled={updatingId === org.id}
                      onChange={(e) =>
                        handlePlanChange(org.id, e.target.value as PlanType)
                      }
                      className="h-9 rounded-lg border border-rule bg-white px-2.5 text-xs font-semibold outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
                    >
                      <option value="starter">Starter</option>
                      <option value="pro">Pro</option>
                      <option value="suspended">Suspended</option>
                    </select>
                  </td>
                  <td className="px-5 py-4 text-mute">
                    <ChevronRight className="h-4 w-4 opacity-0 transition group-hover:opacity-100" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {orgs.length === 0 ? (
          <p className="px-5 py-16 text-center text-sm text-mute">
            No firms registered yet.
          </p>
        ) : null}
      </div>
    </div>
  );
}
