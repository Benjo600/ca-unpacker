import { useEffect, useMemo, useState } from "react";
import { fetchAdminOrgs, isActiveWithinDays, type AdminOrg } from "../../lib/admin";

export default function Overview() {
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAdminOrgs()
      .then(setOrgs)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  const stats = useMemo(() => {
    const active7d = orgs.filter((o) => isActiveWithinDays(o.last_active_at, 7)).length;
    const filesThisMonth = orgs.reduce((sum, o) => sum + o.files_used, 0);
    const starter = orgs.filter((o) => o.plan === "starter").length;
    const pro = orgs.filter((o) => o.plan === "pro").length;

    return {
      total: orgs.length,
      active7d,
      filesThisMonth,
      starter,
      pro,
    };
  }, [orgs]);

  if (loading) {
    return <p className="muted">Loading overview…</p>;
  }

  if (error) {
    return <p className="error">{error}</p>;
  }

  return (
    <div>
      <h1>Overview</h1>
      <p className="muted">Operator snapshot across all registered firms.</p>
      <div className="stat-grid">
        <div className="stat-card">
          <div className="value">{stats.total}</div>
          <div className="label">Total registered firms</div>
        </div>
        <div className="stat-card">
          <div className="value">{stats.active7d}</div>
          <div className="label">Active in last 7 days</div>
        </div>
        <div className="stat-card">
          <div className="value">{stats.filesThisMonth}</div>
          <div className="label">Files processed this month</div>
        </div>
        <div className="stat-card">
          <div className="value">
            {stats.starter} / {stats.pro}
          </div>
          <div className="label">Starter vs Pro</div>
        </div>
      </div>
    </div>
  );
}
