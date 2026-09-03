import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { redirectToDesktop } from "../lib/admin";
import { supabase } from "../lib/supabase";

export default function Signup() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firmName, setFirmName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setLoading(true);

    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { firm_name: firmName } },
    });

    setLoading(false);

    if (signUpError) {
      setError(signUpError.message);
      return;
    }

    if (searchParams.get("redirect") === "desktop" && data.session) {
      redirectToDesktop(data.session);
      return;
    }

    if (data.session) {
      const next = searchParams.get("next");
      navigate(next || "/admin", { replace: true });
      return;
    }

    setMessage("Check your email to confirm your account, then log in.");
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
          <h1>Create account</h1>
          <p className="muted">
            Start with Starter plan — 100 files per month. Processing stays on
            your PC.
          </p>
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
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="firmName">Firm name</label>
              <input
                id="firmName"
                type="text"
                required
                value={firmName}
                onChange={(e) => setFirmName(e.target.value)}
              />
            </div>
            {error && <p className="error">{error}</p>}
            {message && <p className="success">{message}</p>}
            <button type="submit" className="btn btn-ink" disabled={loading}>
              {loading ? "Creating…" : "Sign up"}
            </button>
          </form>
          <p className="muted" style={{ marginTop: 20 }}>
            Already have an account? <Link to="/login">Log in</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
