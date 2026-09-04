import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AuthShell from "../components/AuthShell";
import { Alert, FieldLabel, PrimaryButton, TextInput } from "../components/ui";
import { pathAfterAuth } from "../lib/postAuth";
import { supabase } from "../lib/supabase";

const supabaseConfigured = Boolean(
  import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_ANON_KEY,
);

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;

    async function resume(session: Parameters<typeof pathAfterAuth>[0]) {
      if (!session || cancelled) return;
      const next = await pathAfterAuth(session, searchParams);
      if (cancelled || next === "desktop") return;
      navigate(next, { replace: true });
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      void resume(session);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      void resume(session);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [navigate, searchParams]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!supabaseConfigured) {
      setError(
        "This local app is missing Supabase keys. Use https://ca-unpacker-auth.netlify.app/login or add apps/web/.env.local.",
      );
      return;
    }

    setLoading(true);

    const { data, error: signInError } =
      await supabase.auth.signInWithPassword({ email, password });

    setLoading(false);

    if (signInError) {
      setError(signInError.message);
      return;
    }

    const next = await pathAfterAuth(data.session, searchParams);
    if (next === "desktop") return;
    navigate(next, { replace: true });
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your firm account or the operator console."
      footer={
        <>
          New firm?{" "}
          <Link to="/signup" className="font-semibold text-accent no-underline hover:text-accent-hover">
            Create account
          </Link>
        </>
      }
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        <div>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <TextInput
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <TextInput
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error ? <Alert variant="error">{error}</Alert> : null}
        <PrimaryButton type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Continue"}
        </PrimaryButton>
      </form>
    </AuthShell>
  );
}
