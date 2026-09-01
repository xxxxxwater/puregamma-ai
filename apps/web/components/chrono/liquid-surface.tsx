"use client";

import type { ReactNode } from "react";
import { useChronoTierReactive, useHtmlDataset } from "@/lib/chrono";

/**
 * A reusable "liquid glass" surface: the translucent body plus a refractive
 * top edge (Glass mode only). In Classic mode, or with motion/transparency
 * reduced, it degrades to the plain translucent panel and is effectively a
 * styled section wrapper — it never hides content and never needs JS to
 * render.
 *
 * `chronoSlice` opts the panel into an enclosing ChronoSlices scroll reveal.
 */
export function LiquidSurface({ children, className = "", as: Tag = "section", chronoSlice = false }: {
  children: ReactNode;
  className?: string;
  as?: "section" | "article" | "div";
  chronoSlice?: boolean;
}) {
  const tier = useChronoTierReactive();
  const style = useHtmlDataset("visualStyle");
  const glass = style !== "classic";
  const edge = glass && (tier === "full" || tier === "light") ? "refractive-edge" : "";
  return (
    <Tag
      className={"liquid-surface " + edge + " " + className}
      {...(chronoSlice ? { "data-chrono-slice": true } : {})}
    >
      {children}
    </Tag>
  );
}
