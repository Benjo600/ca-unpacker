import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import PlanBadge from "../../components/PlanBadge";
import { Alert, FieldLabel, PrimaryButton, SelectInput } from "../../components/ui";
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
              file_limit: plan === "pro" ? null : plan === "starter" ? 100 : 0,
            }
          : prev,
      );
      setMessage("Plan updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
    } finally {
      setSaving(false);
    }
  }

  async function toggleSuspend() {
    if (!org) return;
    const next: PlanType = org.plan === "suspended" ? "starter" : "suspended";
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await updateOrgPlan(org.id, next);
      setPlan(next);
      setOrg((prev) =>
        prev
          ? { ...prev, plan: next, file_limit: next === "starter" ? 100 : 0 }
          : prev,
      );
      setMessage(next === "suspended" ? "Account suspended." : "Account restored.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="h-64 animate-pulse rounded-xl bg-rule/40" />;
  }

  if (!org) {
    return (
      <div>
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-bad">
          Firm not found.
        </p>
        <Link
          to="/admin/users"
          className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-mute no-underline hover:text-accent"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to firms
        </Link>
      </div>
    );
  }

  const month = currentMonthLabel();

  return (
    <div>
      <Link
        to="/admin/users"
        className="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-mute no-underline hover:text-accent"
      >
        <ArrowLeft className="h-4 w-4" />
        All firms
      </Link>

      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-accent">
            Firm detail
          </p>
          <h1 className="font-display mt-2 text-4xl tracking-tight text-ink">
            {org.name}
          </h1>
          <p className="mt-1 text-sm text-mute">{org.email}</p>
        </div>
        <PlanBadge plan={org.plan} />
      </header>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {message ? (
        <div className="mb-4">
          <Alert variant="success">{message}</Alert>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-3">
        <section className="rounded-xl border border-rule/80 bg-white p-6 shadow-card lg:col-span-2">
          <h2 className="text-sm font-bold uppercase tracking-wider text-mute">
            Usage · {month}
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div>
              <p className="text-xs text-mute">Files processed</p>
              <p className="font-display tabular-nums mt-1 text-3xl text-ink">
                {org.files_used}
              </p>
            </div>
            <div>
              <p className="text-xs text-mute">Monthly limit</p>
              <p className="font-display tabular-nums mt-1 text-3xl text-ink">
                {formatFileLimit(org.file_limit)}
              </p>
            </div>
            <div>
              <p className="text-xs text-mute">Devices</p>
              <p className="font-display tabular-nums mt-1 text-3xl text-ink">
                {org.device_count}
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-rule/80 bg-white p-6 shadow-card">
          <h2 className="text-sm font-bold uppercase tracking-wider text-mute">
            Account
          </h2>
          <dl className="mt-4 space-y-3 text-sm">
            <div>
              <dt className="text-xs text-mute">Joined</dt>
              <dd className="mt-0.5 font-medium">{formatDate(org.created_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-mute">Last active</dt>
              <dd className="mt-0.5 font-medium">
                {formatDate(org.last_active_at)}
              </dd>
            </div>
          </dl>
        </section>

        <section className="rounded-xl border border-rule/80 bg-white p-6 shadow-card lg:col-span-3">
          <h2 className="text-sm font-bold uppercase tracking-wider text-mute">
            Plan controls
          </h2>
          <form className="mt-5 max-w-md space-y-5" onSubmit={handlePlanSubmit}>
            <div>
              <FieldLabel htmlFor="plan">Subscription plan</FieldLabel>
              <SelectInput
                id="plan"
                value={plan}
                onChange={(e) => setPlan(e.target.value as PlanType)}
              >
                <option value="starter">Starter</option>
                <option value="pro">Pro</option>
                <option value="suspended">Suspended</option>
              </SelectInput>
            </div>
            <div className="flex flex-wrap gap-3">
              <PrimaryButton
                type="submit"
                disabled={saving}
                className="!w-auto px-6"
              >
                {saving ? "Saving…" : "Save plan"}
              </PrimaryButton>
              <button
                type="button"
                disabled={saving}
                onClick={toggleSuspend}
                className="h-11 rounded-lg border border-red-200 bg-red-50 px-6 text-sm font-semibold text-bad transition hover:bg-red-100 disabled:opacity-50"
              >
                {org.plan === "suspended" ? "Restore account" : "Suspend"}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
