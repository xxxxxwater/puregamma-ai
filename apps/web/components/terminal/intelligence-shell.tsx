import type { ReactNode } from "react";
import { Display, DisplayEyebrow } from "@/components/terminal/editorial";

/**
 * Shared intelligence-workspace frame (Chat / Research / Secretary).
 * A modern product header — eyebrow, tight display title, one byline —
 * then the working surface. No decorative rules, no card chrome.
 */
export function IntelligenceShell({ eyebrow, title, children, byline }: {
  eyebrow: string;
  title: string;
  byline?: string;
  children: ReactNode;
}) {
  return (
    <div className="intelligence-shell">
      <header className="mb-8">
        <DisplayEyebrow>{eyebrow}</DisplayEyebrow>
        <Display as="h1" size="lg" className="mt-3">{title}</Display>
        {byline ? <p className="mt-3 max-w-2xl text-[0.92rem] leading-7 text-muted">{byline}</p> : null}
      </header>
      {children}
    </div>
  );
}
