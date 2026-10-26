import type { PlanType } from "../lib/admin";

const STYLES: Record<PlanType, string> = {
  starter: "bg-stone-100 text-ink ring-1 ring-stone-200",
  pro: "bg-emerald-50 text-ok ring-1 ring-emerald-200",
  suspended: "bg-red-50 text-bad ring-1 ring-red-200",
};

export default function PlanBadge({ plan }: { plan: PlanType }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${STYLES[plan]}`}
    >
      {plan}
    </span>
  );
}
