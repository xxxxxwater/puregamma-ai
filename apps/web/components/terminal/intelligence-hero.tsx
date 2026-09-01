"use client";

import type { ReactNode } from "react";

import { Display, DisplayEyebrow } from "@/components/terminal/editorial";
import { CommandSurface } from "@/components/terminal/command-surface";
import { MarketPresence } from "@/components/terminal/market-presence";
import type { MarketStatus } from "@/lib/chrono";
import type { Locale } from "@/i18n/routing";

/**
 * The dashboard hero: an open intelligence workspace, not a centered title.
 * Presence (top-right) -> huge modern sans headline -> honest byline ->
 * the AI command lens. Each stage is a stage of the ChronoEntrance timeline.
 */
export function IntelligenceHero({ locale, eyebrow, title, byline, status, dataAsOf, liveLabel }: {
  locale: Locale;
  eyebrow: string;
  title: string;
  byline: string;
  status?: MarketStatus;
  dataAsOf?: string | null;
  liveLabel?: string | null;
}) {
  return (
    <div className="hub-hero">
      <MotionStage className="flex flex-wrap items-end justify-between gap-4">
        <DisplayEyebrow>{eyebrow}</DisplayEyebrow>
        <MarketPresence locale={locale} status={status} dataAsOf={dataAsOf} liveLabel={liveLabel} />
      </MotionStage>
      <MotionStage><Display as="h1" size="xl" className="mt-7 max-w-4xl">{title}</Display></MotionStage>
      <MotionStage><p className="mt-6 max-w-xl text-[0.96rem] leading-7 text-muted">{byline}</p></MotionStage>
      <MotionStage className="mt-8 max-w-2xl"><CommandSurface locale={locale} /></MotionStage>
    </div>
  );
}

/** Inline stage marker (wrapped so the hero stays one semantic unit). */
function MotionStage({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={className} data-chrono-enter>{children}</div>;
}