import clsx from "clsx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={clsx("border border-border-pg bg-bg-panel p-4", className)}>{children}</section>;
}

export function Button({
  children,
  className = "",
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  return (
    <button
      className={clsx(
        "inline-flex min-h-10 items-center justify-center gap-2 border px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "border-border-pg-strong bg-pg-white text-pg-black hover:bg-pg-white-soft",
        variant === "secondary" && "border-border-pg bg-bg-panel-muted text-text-pg hover:border-border-pg-strong",
        variant === "danger" && "border-border-pg-strong bg-bg-panel text-status-negative hover:border-border-pg-strong",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx("w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong", className)} {...props} />;
}

export function Select({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={clsx("w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg outline-none focus:border-border-pg-strong", className)} {...props}>{children}</select>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-text-pg-muted">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-xs text-text-pg-dim">{hint}</span> : null}
    </label>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "positive" | "warning" | "danger" }) {
  return (
    <span
      className={clsx(
        "inline-flex rounded-full border px-2 py-0.5 text-xs font-medium",
        tone === "neutral" && "border-border-pg bg-bg-panel-muted text-text-pg-muted",
        tone === "positive" && "border-border-pg bg-bg-panel text-status-positive",
        tone === "warning" && "border-border-pg bg-bg-panel text-status-warning",
        tone === "danger" && "border-border-pg bg-bg-panel text-status-negative"
      )}
    >
      {children}
    </span>
  );
}

export function SectionTitle({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <h1 className="text-xl font-semibold tracking-normal">{title}</h1>
      {meta ? <span className="text-sm text-text-pg-muted">{meta}</span> : null}
    </div>
  );
}
