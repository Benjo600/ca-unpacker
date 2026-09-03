import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabase";

export default function AdminLayout() {
  const navigate = useNavigate();

  async function handleLogout() {
    await supabase.auth.signOut();
    navigate("/login", { replace: true });
  }

  return (
    <div className="center-page">
      <header className="top">
        <div className="wrap">
          <span className="brand">CA Unpacker — Admin</span>
          <nav>
            <button
              type="button"
              className="btn btn-tab"
              style={{ marginLeft: 20 }}
              onClick={handleLogout}
            >
              Log out
            </button>
          </nav>
        </div>
      </header>
      <main style={{ display: "block", width: "100%" }}>
        <div className="wrap" style={{ paddingTop: 32, paddingBottom: 48 }}>
          <nav className="admin-nav">
            <NavLink
              to="/admin"
              end
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              Overview
            </NavLink>
            <NavLink
              to="/admin/users"
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              Users
            </NavLink>
          </nav>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
