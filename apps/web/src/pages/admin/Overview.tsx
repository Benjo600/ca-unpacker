import { useEffect, useMemo, useState } from "react";
import { Activity, Building2, FileStack, Sparkles } from "lucide-react";
import { fetchAdminOrgs, isActiveWithinDays, type AdminOrg } from "../../lib/admin";

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
}) {
  return (
    <div className="rounded-xl border border-rule/80 bg-white p-6 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-mute">
            {label}
          </p>
          <p className="font-display tabular-nums mt-2 text-4xl tracking-tight text-ink">
            {value}
          </p>
        </div>
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-paper text-accent ring-1 ring-rule/60">
          <Icon className="h-5 w-5" strokeWidth={1.75} />
        </span>
      </div>
    </div>
  );
}

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
    return { total: orgs.length, active7d, filesThisMonth, starter, pro };
  }, [orgs]);

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-32 animate-pulse rounded-xl bg-rule/40"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-bad">
        {error}
      </p>
    );
  }

  return (
    <div>
      <header className="mb-10">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-accent">
          Dashboard
        </p>
        <h1 className="font-display mt-2 text-4xl tracking-tight text-ink">
          Overview
        </h1>
        <p className="mt-2 max-w-xl text-sm text-mute">
          Registered firms, weekly activity, and platform-wide file usage.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Registered firms" value={stats.total} icon={Building2} />
        <StatCard label="Active · 7 days" value={stats.active7d} icon={Activity} />
        <StatCard label="Files this month" value={stats.filesThisMonth} icon={FileStack} />
        <StatCard
          label="Starter / Pro"
          value={`${stats.starter} / ${stats.pro}`}
          icon={Sparkles}
        />
      </div>
    </div>
  );
}
