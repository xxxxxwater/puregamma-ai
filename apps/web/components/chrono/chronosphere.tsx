"use client";

import { useChronoTierReactive, useHtmlDataset } from "@/lib/chrono";

/**
 * Global "Liquid Chronosphere" backdrop for the app shell (Glass mode only).
 *
 * Renders one fixed, pointer-transparent layer of layered liquid light fields
 * plus a slow refractive sheen. Everything is pure CSS: gradients + an inline
 * SVG film-grain/refracition filter — no WebGL, no Three.js, no images.
 *
 * Degradation:
 *  - Classic style  -> not rendered at all (the shell keeps its static ambient).
 *  - static tier    -> a single static gradient field (no blur, no sheen).
 *  - light tier     -> static gradient field tuned to cold blue.
 *  - full tier      -> slow drifting fields + refractive sheen band.
 */
export function Chronosphere() {
  const tier = useChronoTierReactive();
  const style = useHtmlDataset("visualStyle");
  if (style === "classic") return null;
  const motion = tier === "full";
  return (
    <div aria-hidden className={"chronosphere" + (motion ? " chronosphere-motion" : "")} data-tier={tier}>
      <div className="chronosphere-field" />
    </div>
  );
}