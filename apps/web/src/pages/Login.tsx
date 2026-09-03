import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { redirectToDesktop } from "../lib/admin";
import { supabase } from "../lib/supabase";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const { data, error: signInError } =
      await supabase.auth.signInWithPassword({
        email,
        password,
      });

    setLoading(false);

    if (signInError) {
      setError(signInError.message);
      return;
    }

    if (searchParams.get("redirect") === "desktop" && data.session) {
      redirectToDesktop(data.session);
      return;
    }

    const next = searchParams.get("next") || "/admin";
    navigate(next, { replace: true });
  }

  return (
    <div className="center-page">
      <header className="top">
        <div className="wrap">
          <Link to="/" className="brand">
            CA Unpacker
          </Link>
        </div>
      </header>
      <main>
        <div className="docket">
          <h1>Log in</h1>
          <p className="muted">Sign in to your CA Unpacker account.</p>
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && <p className="error">{error}</p>}
            <button type="submit" className="btn btn-ink" disabled={loading}>
              {loading ? "Signing in…" : "Log in"}
            </button>
          </form>
          <p className="muted" style={{ marginTop: 20 }}>
            New firm? <Link to="/signup">Create account</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
