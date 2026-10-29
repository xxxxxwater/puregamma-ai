import clsx from "clsx";
import { forwardRef } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={clsx("rounded-2xl border border-border-pg bg-bg-panel p-5 shadow-card", className)}>{children}</section>;
}

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  // Only secondary draws a (neutral) border; the others are borderless, so a
  // variant switch never shifts layout by a border width.
  primary: "bg-[var(--pg-surface-inverse)] text-[var(--pg-text-inverse)] hover:opacity-[.92]",
  secondary: "border border-border-pg-strong bg-bg-panel-muted text-text-pg hover:bg-[var(--pg-surface-hover)]",
  ghost: "bg-transparent text-text-pg-muted hover:bg-[var(--pg-surface-hover)] hover:text-text-pg",
  danger: "bg-[var(--pg-danger-soft)] text-status-negative hover:bg-[color-mix(in_oklab,var(--pg-danger)_20%,transparent)]",
};
const BUTTON_SIZE: Record<ButtonSize, { height: string; width: string; padding: string; text: string }> = {
  sm: { height: "min-h-control-sm", width: "w-control-sm", padding: "px-2.5", text: "text-12" },
  md: { height: "min-h-control-md", width: "w-control-md", padding: "px-4", text: "text-14" },
  lg: { height: "min-h-control-lg", width: "w-control-lg", padding: "px-5", text: "text-14" },
};
/* Without a class-merging dependency, a call-site class in one of these groups
   replaces the Button's own default for that group (Tailwind's CSS order, not
   attribute order, would otherwise decide: `inline-flex` beats `block`,
   `gap-2` beats `gap-1.5`). Colours and states always stay the variant's. */
type Group = "display" | "items" | "gap" | "font" | "justify" | "radius" | "height" | "width" | "padding" | "text";
// Unprefixed only: `lg:hidden` / `sm:px-6` sit in later media/state rules and
// already win where they apply, so they must not remove the base default.
const prefix = "(^|\\s)";
const OVERRIDABLE: [RegExp, Group][] = [
  [new RegExp(`${prefix}(?:block|inline-block|inline|flex|inline-flex|grid|inline-grid|hidden|contents|table)(?=\\s|$)`), "display"],
  [new RegExp(`${prefix}items-`), "items"],
  [new RegExp(`${prefix}gap-`), "gap"],
  [new RegExp(`${prefix}font-(?:thin|extralight|light|normal|medium|semibold|bold|extrabold|black)(?=\\s|$)`), "font"],
  [new RegExp(`${prefix}justify-`), "justify"],
  [new RegExp(`${prefix}rounded`), "radius"],
  [new RegExp(`${prefix}(?:min-h|h|size)-`), "height"],
  [new RegExp(`${prefix}(?:w|size)-`), "width"],
  [new RegExp(`${prefix}p[xlr]?-`), "padding"],
  [new RegExp(`${prefix}text-(?:\\d|xs|sm|base|lg|xl|2xl|2xs|\\[\\d)`), "text"],
];

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize; iconOnly?: boolean };

/** The one button: four variants × three sizes. `iconOnly` makes a square of the size's height. Forwards its ref (focus return, menus). */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { children, className = "", variant = "primary", size = "md", iconOnly = false, ...props },
  ref
) {
  const own = new Set(OVERRIDABLE.filter(([pattern]) => pattern.test(className)).map(([, group]) => group));
  const metrics = BUTTON_SIZE[size];
  const unless = (group: Group, value: string) => (own.has(group) ? false : value);
  return (
    <button
      ref={ref}
      className={clsx(
        "transition-[background-color,border-color,box-shadow,opacity] duration-[120ms] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-text-pg disabled:cursor-not-allowed disabled:opacity-50",
        unless("display", "inline-flex"),
        unless("items", "items-center"),
        unless("gap", "gap-2"),
        unless("font", "font-medium"),
        unless("justify", "justify-center"),
        unless("radius", "rounded-md"),
        unless("height", metrics.height),
        unless("text", metrics.text),
        iconOnly ? unless("width", metrics.width) : unless("padding", metrics.padding),
        BUTTON_VARIANT[variant],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
});

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx("w-full rounded-xl border border-border-pg bg-bg-panel-muted px-3.5 py-2.5 text-sm text-text-pg placeholder:text-text-pg-dim outline-none transition focus:border-border-pg-strong focus:ring-2 focus:ring-accent-ring", className)} {...props} />;
}

export function Select({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={clsx("w-full rounded-xl border border-border-pg bg-bg-panel-muted px-3.5 py-2.5 text-sm text-text-pg outline-none transition focus:border-border-pg-strong focus:ring-2 focus:ring-accent-ring", className)} {...props}>{children}</select>;
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
