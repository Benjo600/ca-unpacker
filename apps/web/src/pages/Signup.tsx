import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AuthShell from "../components/AuthShell";
import { Alert, FieldLabel, PrimaryButton, TextInput } from "../components/ui";
import { pathAfterAuth } from "../lib/postAuth";
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

    if (data.session) {
      const next = await pathAfterAuth(data.session, searchParams);
      if (next === "desktop") return;
      navigate(next, { replace: true });
      return;
    }

    setMessage("Check your email to confirm, then log in.");
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Starter includes 100 files per month. Track usage on your dashboard after you sign in."
      footer={
        <>
          Already registered?{" "}
          <Link to="/login" className="font-semibold text-accent no-underline hover:text-accent-hover">
            Log in
          </Link>
        </>
      }
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        <div>
          <FieldLabel htmlFor="firmName">Firm name</FieldLabel>
          <TextInput
            id="firmName"
            type="text"
            required
            autoComplete="organization"
            placeholder="Sharma & Associates"
            value={firmName}
            onChange={(e) => setFirmName(e.target.value)}
          />
        </div>
        <div>
          <FieldLabel htmlFor="email">Work email</FieldLabel>
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
            autoComplete="new-password"
            required
            minLength={8}
            placeholder="Minimum 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error ? <Alert variant="error">{error}</Alert> : null}
        {message ? <Alert variant="success">{message}</Alert> : null}
        <PrimaryButton type="submit" disabled={loading}>
          {loading ? "Creating account…" : "Create account"}
        </PrimaryButton>
      </form>
    </AuthShell>
  );
}
