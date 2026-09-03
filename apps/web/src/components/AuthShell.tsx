import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Lock, Monitor, Shield } from "lucide-react";

interface AuthShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}

const TRUST_POINTS = [
  {
    icon: Monitor,
    title: "Local processing",
    body: "Bank PDFs and invoices never leave the CA's laptop.",
  },
  {
    icon: Shield,
    title: "Metadata only",
    body: "We track usage counts — not document contents.",
  },
  {
    icon: Lock,
    title: "Starter included",
    body: "100 files per month to evaluate before upgrading.",
  },
] as const;

export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: AuthShellProps) {
  return (
    <div className="flex min-h-dvh">
      <aside className="relative hidden w-[44%] min-w-[320px] flex-col justify-between overflow-hidden bg-desk p-10 text-desk-ink lg:flex xl:p-14">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 20%, #c45a2a 0%, transparent 45%), radial-gradient(circle at 80% 80%, #c8d2cb 0%, transparent 40%)",
          }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />

        <div className="relative">
          <Link
            to="/signup"
            className="font-display text-3xl tracking-tight text-paper no-underline"
          >
            CA Unpacker
          </Link>
          <p className="mt-1 text-xs font-semibold uppercase tracking-[0.2em] text-desk-ink/70">
            Pre-accounting for CA firms
          </p>
        </div>

        <div className="relative space-y-8">
          <p className="font-display max-w-sm text-[2rem] leading-[1.15] tracking-tight text-paper">
            Control the firm. Never the client files.
          </p>
          <ul className="space-y-5">
            {TRUST_POINTS.map(({ icon: Icon, title: pointTitle, body }) => (
              <li key={pointTitle} className="flex gap-4">
                <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/8 ring-1 ring-white/10">
                  <Icon className="h-4 w-4 text-accent" strokeWidth={2} />
                </span>
                <div>
                  <p className="text-sm font-semibold text-paper">{pointTitle}</p>
                  <p className="mt-0.5 text-sm leading-snug text-desk-ink/90">
                    {body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-desk-ink/60">
          © CA Unpacker · Documents processed locally
        </p>
      </aside>

      <main className="flex flex-1 flex-col items-center justify-center bg-paper-bright px-5 py-12 sm:px-8">
        <div className="mb-8 w-full max-w-[420px] lg:hidden">
          <Link
            to="/signup"
            className="font-display text-2xl tracking-tight text-ink no-underline"
          >
            CA Unpacker
          </Link>
        </div>

        <div className="w-full max-w-[420px] rounded-2xl border border-rule/80 bg-white p-8 shadow-elevated sm:p-10">
          <header className="mb-8">
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-accent">
              Account
            </p>
            <h1 className="font-display mt-2 text-[2rem] leading-tight tracking-tight text-ink">
              {title}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-mute">{subtitle}</p>
          </header>

          {children}

          {footer ? (
            <footer className="mt-8 border-t border-rule pt-6 text-center text-sm text-mute">
              {footer}
            </footer>
          ) : null}
        </div>
      </main>
    </div>
  );
}
