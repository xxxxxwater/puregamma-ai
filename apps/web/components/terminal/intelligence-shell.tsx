import type { ReactNode } from "react";
import { Display, DisplayEyebrow } from "@/components/terminal/editorial";

/**
 * Shared intelligence-workspace frame (Chat / Research / Secretary).
 * A modern product header — eyebrow, tight display title, one byline —
 * then the working surface. No decorative rules, no card chrome.
 *
 * `compact` shrinks that header for surfaces whose working area must fit the
 * viewport. Chat passes it: at 1440x900 the full-height header pushed the
 * composer ~110px below the fold, so the product's primary control could not be
 * reached without scrolling. The header collapses to a single line instead of
 * being removed, so the surface still identifies itself.
 */
export function IntelligenceShell({ eyebrow, title, children, byline, compact = false }: {
  eyebrow: string;
  title: string;
  byline?: string;
  children: ReactNode;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <div className="intelligence-shell mx-auto w-full max-w-[1180px]">
        <header className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <DisplayEyebrow>{eyebrow}</DisplayEyebrow>
          <Display as="h1" size="md" className="!text-[1.05rem] leading-6">{title}</Display>
          {byline ? <p className="hidden text-xs leading-5 text-muted md:block">{byline}</p> : null}
        </header>
        {children}
      </div>
    );
  }
  return (
    <div className={compact ? "intelligence-shell mx-auto w-full max-w-[1180px]" : "intelligence-shell"}>
      <header className="mb-8">
        <DisplayEyebrow>{eyebrow}</DisplayEyebrow>
        <Display as="h1" size="lg" className="mt-3">{title}</Display>
        {byline ? <p className="mt-3 max-w-2xl text-[0.92rem] leading-7 text-muted">{byline}</p> : null}
      </header>
      {children}
    </div>
  );
}
