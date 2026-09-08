export const PLAN_LIMITS: Record<string, number | null> = {
  starter: 100,
  pro: null,
  suspended: 0,
};

export const VALID_PLANS = ["starter", "pro", "suspended"] as const;
export type PlanType = (typeof VALID_PLANS)[number];

export function currentMonth(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function fileLimitForPlan(plan: string): number | null {
  return PLAN_LIMITS[plan] ?? null;
}
