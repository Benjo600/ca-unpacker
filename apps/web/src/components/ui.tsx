import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";

export function FieldLabel({
  htmlFor,
  children,
}: {
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="mb-2 block text-xs font-semibold uppercase tracking-wider text-mute"
    >
      {children}
    </label>
  );
}

export function TextInput({
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`h-11 w-full rounded-lg border border-rule bg-paper-bright px-3.5 text-[15px] text-ink outline-none transition placeholder:text-mute/50 focus:border-accent focus:ring-4 focus:ring-accent/15 ${className}`}
      {...props}
    />
  );
}

export function SelectInput({
  className = "",
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`h-11 w-full rounded-lg border border-rule bg-paper-bright px-3.5 text-[15px] text-ink outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/15 ${className}`}
      {...props}
    />
  );
}

export function PrimaryButton({
  children,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`flex h-11 w-full items-center justify-center rounded-lg bg-ink text-sm font-semibold text-paper transition hover:bg-[#0f1c17] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Alert({
  variant,
  children,
}: {
  variant: "error" | "success";
  children: React.ReactNode;
}) {
  const styles =
    variant === "error"
      ? "border-red-200 bg-red-50 text-bad"
      : "border-emerald-200 bg-emerald-50 text-ok";
  return (
    <p className={`rounded-lg border px-3.5 py-3 text-sm ${styles}`}>
      {children}
    </p>
  );
}
