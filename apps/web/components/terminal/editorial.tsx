import type { ReactNode } from "react";

/** Editorial primitives for the Intelligence Terminal: a tight modern
 * display, a tracked section label, hairline rules and a quiet panel. These are
 * deliberately plain (no client hooks) so they work in any surface tier. */

export function Display({ children, as: Tag = "h1", size: s = "md", className = "" }: { children: ReactNode; as?: "h1" | "h2" | "h3" | "p"; size?: "sm" | "md" | "lg" | "xl"; className?: string }) {
  const sizeClass = s === "xl" ? "display-xl" : s === "lg" ? "display-lg" : s === "sm" ? "display-sm" : "display-md";
  return <Tag className={sizeClass + " " + className}>{children}</Tag>;
}

export function DisplayEyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={"section-eyebrow " + className}>{children}</div>;
}

export function SectionLabel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={"section-label " + className}>{children}</div>;
}

export function Rule({ className = "" }: { className?: string }) {
  return <hr className={"editorial-rule " + className} />;
}

export function TerminalPanel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={"terminal-panel " + className}>{children}</section>;
}
