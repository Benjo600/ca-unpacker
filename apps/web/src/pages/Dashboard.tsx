import { useEffect, useMemo, useState } from "react";
import { FileStack, Monitor, Shield } from "lucide-react";
import PlanBadge from "../components/PlanBadge";
import { Alert } from "../components/ui";
import { fetchAccountSnapshot, type AccountSnapshot } from "../lib/account";
import { formatDate, formatFileLimit } from "../lib/admin";

function usagePercent(used: number, limit: number | null): number {
  if (limit === null) return 8;
  if (limit <= 0) return 100;
  return Math.min(100, Math.round((used / limit) * 100));
}

export default function Dashboard() {
  const [account, setAccount] = useState<AccountSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAccountSnapshot()
      .then(setAccount)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  const barWidth = useMemo(() => {
    if (!account) return 0;
    return usagePercent(account.filesUsed, account.fileLimit);
  }, [account]);

  if (loading) {
    return <div className="h-64 animate-pulse rounded-xl bg-rule/40" />;
  }

  if (error || !account) {
    return (
      <Alert variant="error">{error || "Could not load your account."}</Alert>
    );
  }

  const remainingLabel =
    account.plan === "suspended"
      ? "Ingest is blocked"
      : account.fileLimit === null
        ? "Unlimited this month"
        : `${account.filesRemaining} of ${account.fileLimit} remaining`;

  return (
    <div>
      <header className="mb-10 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-accent">
            Your firm
          </p>
          <h1 className="font-display mt-2 text-4xl tracking-tight text-ink">
            {account.firmName}
          </h1>
          <p className="mt-1 text-sm text-mute">{account.email}</p>
        </div>
        <PlanBadge plan={account.plan} />
      </header>

      {account.plan === "suspended" ? (
        <div className="mb-6">
          <Alert variant="error">
            This account is suspended. Contact support before processing more files.
          </Alert>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-3">
        <section className="rounded-xl border border-rule/80 bg-white p-6 shadow-card lg:col-span-2">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-mute">
                Files this month · {account.month}
              </p>
              <p className="font-display tabular-nums mt-2 text-5xl tracking-tight text-ink">
                {account.filesUsed}
                <span className="ml-2 text-2xl text-mute">
                  / {formatFileLimit(account.fileLimit)}
                </span>
              </p>
              <p className="mt-2 text-sm text-mute">{remainingLabel}</p>
            </div>
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-paper text-accent ring-1 ring-rule/60">
              <FileStack className="h-5 w-5" strokeWidth={1.75} />
            </span>
          </div>
          <div className="mt-6 h-2.5 overflow-hidden rounded-full bg-paper">
            <div
              className="h-full rounded-full bg-accent transition-[width]"
              style={{ width: `${barWidth}%` }}
            />
          </div>
          <p className="mt-4 text-sm leading-relaxed text-mute">
            Usage is counted when you dump files in the desktop app. Client PDFs,
            invoices, and extracted rows never leave that PC — only this counter
            is synced here.
          </p>
        </section>

        <section className="rounded-xl border border-rule/80 bg-white p-6 shadow-card">
          <p className="text-xs font-semibold uppercase tracking-wider text-mute">
            Plan
          </p>
          <p className="font-display mt-2 text-3xl tracking-tight text-ink capitalize">
            {account.plan}
          </p>
          <p className="mt-2 text-sm text-mute">
            {account.plan === "pro"
              ? "Unlimited files. Same local processing as Starter."
              : account.plan === "starter"
                ? "Starter includes 100 files each calendar month."
                : "Processing is paused until the plan is restored."}
          </p>
          <dl className="mt-6 space-y-3 text-sm">
            <div>
              <dt className="text-xs text-mute">Joined</dt>
              <dd className="mt-0.5 font-medium">{formatDate(account.createdAt)}</dd>
            </div>
            <div>
              <dt className="text-xs text-mute">Last desktop activity</dt>
              <dd className="mt-0.5 font-medium">
                {formatDate(account.lastActiveAt)}
              </dd>
            </div>
          </dl>
        </section>

        <section className="rounded-xl border border-rule/80 bg-white p-6 shadow-card lg:col-span-2">
          <div className="mb-4 flex items-center gap-2">
            <Shield className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-sm font-bold uppercase tracking-wider text-mute">
              Monthly history
            </h2>
          </div>
          {account.usageHistory.length === 0 ? (
            <p className="text-sm text-mute">
              No dumps recorded yet. Sign in on the Windows app and process a
              client month — the count will appear here.
            </p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-rule text-[10px] font-bold uppercase tracking-wider text-mute">
                  <th className="py-2">Month</th>
                  <th className="py-2">Files processed</th>
                  <th className="py-2">Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule/80">
                {account.usageHistory.map((row) => (
                  <tr key={row.month}>
                    <td className="py-3 font-semibold">{row.month}</td>
                    <td className="tabular-nums py-3">{row.files_processed}</td>
                    <td className="py-3 text-mute">{formatDate(row.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="rounded-xl border border-rule/80 bg-white p-6 shadow-card">
          <div className="mb-4 flex items-center gap-2">
            <Monitor className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-sm font-bold uppercase tracking-wider text-mute">
              This account’s PCs
            </h2>
          </div>
          {account.devices.length === 0 ? (
            <p className="text-sm text-mute">
              Open CA Unpacker on Windows while signed in to register this PC.
            </p>
          ) : (
            <ul className="space-y-3">
              {account.devices.map((device) => (
                <li key={device.id} className="text-sm">
                  <p className="font-semibold text-ink">
                    {device.label || "Windows PC"}
                  </p>
                  <p className="text-mute">
                    {device.app_version || "app"} · last seen{" "}
                    {formatDate(device.last_seen_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
