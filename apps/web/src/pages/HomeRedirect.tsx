import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import AuthShell from "../components/AuthShell";
import { defaultSignedInPath } from "../lib/admin";
import { supabase } from "../lib/supabase";

export default function HomeRedirect() {
  const [to, setTo] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function resolve() {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        if (!cancelled) setTo("/login");
        return;
      }
      const path = await defaultSignedInPath();
      if (!cancelled) setTo(path);
    }

    resolve();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!to) {
    return (
      <AuthShell title="CA Unpacker" subtitle="Checking your session…">
        <div className="flex justify-center py-8">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-rule border-t-accent" />
        </div>
      </AuthShell>
    );
  }

  return <Navigate to={to} replace />;
}
