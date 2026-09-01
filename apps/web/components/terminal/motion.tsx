import type { ReactNode } from "react";

/** Marks a block as one stage of the main entrance timeline (ChronoEntrance).
 * Glass-only; no-op elsewhere. Content is never hidden server-side. */
export function MotionReveal({ children, className = "", as: Tag = "div" }: { children: ReactNode; className?: string; as?: "div" | "section" | "p" }) {
  return <Tag className={className} data-chrono-enter>{children}</Tag>;
}

/** Asymmetric open grid for the data workstations. */
export function DataWorkbench({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={"workbench-grid " + className}>{children}</div>;
}

/** The floating chrome wrapper (top bar / command menus). Glass in Glass mode. */
export function FloatingChrome({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={"shell-chrome " + className}>{children}</div>;
}
