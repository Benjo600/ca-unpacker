import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, LogOut, Users } from "lucide-react";
import { supabase } from "../lib/supabase";

const NAV: Array<{
  to: string;
  end?: boolean;
  label: string;
  icon: typeof LayoutDashboard;
}> = [
  { to: "/admin", end: true, label: "Overview", icon: LayoutDashboard },
  { to: "/admin/users", label: "Firms", icon: Users },
];

export default function AdminLayout() {
  const navigate = useNavigate();

  async function handleLogout() {
    await supabase.auth.signOut();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-dvh bg-paper-bright">
      <aside className="flex w-64 shrink-0 flex-col border-r border-rule/80 bg-desk text-desk-ink">
        <div className="border-b border-white/8 px-6 py-6">
          <p className="font-display text-xl tracking-tight text-paper">
            CA Unpacker
          </p>
          <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.18em] text-desk-ink/70">
            Operator console
          </p>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {NAV.map(({ to, end, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold no-underline transition ${
                  isActive
                    ? "bg-accent/20 text-paper"
                    : "text-desk-ink hover:bg-white/6 hover:text-paper"
                }`
              }
            >
              <Icon className="h-4 w-4 shrink-0 opacity-80" strokeWidth={2} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-white/8 p-3">
          <Link
            to="/app"
            className="mb-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold text-desk-ink no-underline transition hover:bg-white/6 hover:text-paper"
          >
            Firm dashboard
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold text-desk-ink transition hover:bg-white/6 hover:text-paper"
          >
            <LogOut className="h-4 w-4" strokeWidth={2} />
            Log out
          </button>
        </div>
      </aside>

      <div className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-6xl px-6 py-10 sm:px-10">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
