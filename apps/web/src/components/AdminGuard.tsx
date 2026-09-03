import { useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { AdminForbiddenError, fetchAdminOrgs } from "../lib/admin";
import { supabase } from "../lib/supabase";

interface AdminGuardProps {
  children: ReactNode;
}

export default function AdminGuard({ children }: AdminGuardProps) {
  const location = useLocation();
  const [status, setStatus] = useState<"loading" | "ok" | "forbidden" | "anon">(
    "loading",
  );

  useEffect(() => {
    let cancelled = false;

    async function verify() {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session) {
        if (!cancelled) setStatus("anon");
        return;
      }

      try {
        await fetchAdminOrgs();
        if (!cancelled) setStatus("ok");
      } catch (err) {
        if (err instanceof AdminForbiddenError) {
          if (!cancelled) setStatus("forbidden");
          return;
        }
        console.error(err);
        if (!cancelled) setStatus("forbidden");
      }
    }

    verify();

    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") {
    return (
      <div className="center-page">
        <header className="top">
          <div className="wrap">
            <span className="brand">CA Unpacker</span>
          </div>
        </header>
        <main>
          <p className="muted">Checking access…</p>
        </main>
      </div>
    );
  }

  if (status === "anon") {
    const next = encodeURIComponent(location.pathname);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  if (status === "forbidden") {
    return (
      <div className="center-page">
        <header className="top">
          <div className="wrap">
            <span className="brand">CA Unpacker</span>
          </div>
        </header>
        <main>
          <div className="docket">
            <h1>Not an admin</h1>
            <p className="muted">
              This dashboard is restricted to operator accounts. Contact support
              if you believe this is an error.
            </p>
          </div>
        </main>
      </div>
    );
  }

  return <>{children}</>;
}
