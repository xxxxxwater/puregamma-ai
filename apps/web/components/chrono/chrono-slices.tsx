"use client";

import { useRef, type ReactNode } from "react";
import { gsap, ScrollTrigger, useGSAP } from "@/components/chrono/motion";
import { useChronoTierReactive, useHtmlDataset } from "@/lib/chrono";

/**
 * Scroll "time-slice" narrative for exploration surfaces.
 *
 * Reveals any descendant carrying `data-chrono-slice` (or the class
 * `chrono-slice`) as it scrolls into view: a short opacity + translateY
 * settle, batched so siblings entering together reveal as one pulse.
 *
 * Safety / degradation:
 *  - Only runs when the visual style is glass, motion is allowed and the
 *    viewport is desktop. Otherwise it is a complete no-op — content stays
 *    fully visible and static (no hidden content, no SSR layout shift).
 *  - Uses ScrollTrigger.batch with `once: true`; kills everything on unmount
 *    via the useGSAP context revert.
 *  - Financial / security surfaces should NOT wrap content in this component.
 */
export function ChronoSlices({ children, className = "" }: { children: ReactNode; className?: string }) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const tier = useChronoTierReactive();
  const style = useHtmlDataset("visualStyle");

  useGSAP(() => {
    if (style === "classic" || tier === "static" || !rootRef.current) return;
    const slices = Array.from(rootRef.current.querySelectorAll<HTMLElement>("[data-chrono-slice], .chrono-slice"));
    if (!slices.length) return;
    gsap.set(slices, { opacity: 0, y: 22 });
    ScrollTrigger.batch(slices, {
      start: "top 90%",
      once: true,
      interval: 0.07,
      onEnter: (batch) =>
        gsap.to(batch, { opacity: 1, y: 0, duration: 0.65, ease: "power2.out", stagger: 0.07, overwrite: true }),
    });
    requestAnimationFrame(() => ScrollTrigger.refresh());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, { scope: rootRef, dependencies: [tier, style] });

  return (
    <div ref={rootRef} className={className}>
      {children}
    </div>
  );
}

/**
 * A single, deliberately-marked time-slice. Wrap a panel/block in this and it
 * will be revealed by an enclosing ChronoSlices as it scrolls into view. On a
 * static/classic/reduced-motion environment it renders nothing extra and the
 * content stays visible.
 */
export function ChronoSlice({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={"chrono-slice " + className} data-chrono-slice>{children}</div>;
}
