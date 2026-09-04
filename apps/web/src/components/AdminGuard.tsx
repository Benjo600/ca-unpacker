import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import AuthShell from "./AuthShell";
import { Alert } from "./ui";
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
        if (!cancelled) setStatus("forbidden");
        if (!(err instanceof AdminForbiddenError)) console.error(err);
      }
    }

    verify();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") {
    return (
      <AuthShell title="Verifying access" subtitle="Checking operator credentials…">
        <div className="flex justify-center py-8">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-rule border-t-accent" />
        </div>
      </AuthShell>
    );
  }

  if (status === "anon") {
    const next = encodeURIComponent(location.pathname);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  if (status === "forbidden") {
    return (
      <AuthShell
        title="Access denied"
        subtitle="This console is restricted to CA Unpacker operators."
        footer={
          <Link to="/app" className="font-semibold text-accent no-underline">
            Open your firm dashboard
          </Link>
        }
      >
        <Alert variant="error">
          Your email is not on the operator allowlist.
        </Alert>
      </AuthShell>
    );
  }

  return <>{children}</>;
}
