"use client";

import { useRef, type ReactNode } from "react";
import { gsap, useGSAP } from "@/components/chrono/motion";
import { useChronoTierReactive, useHtmlDataset } from "@/lib/chrono";

/**
 * Above-the-fold "stage" sequence for an exploration hero: a weighted, non-
 * bouncy timeline that reveals each `[data-chrono-enter]` descendant in DOM
 * order (environment light field -> time core -> core data -> secondary).
 *
 * Runs only in Glass + allowed-motion desktop. Otherwise it is a no-op and
 * content is fully visible. Cleanup is automatic through the useGSAP context
 * revert.
 */
export function ChronoEntrance({ children, className = "" }: { children: ReactNode; className?: string }) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const tier = useChronoTierReactive();
  const style = useHtmlDataset("visualStyle");

  useGSAP(() => {
    if (style === "classic" || tier === "static" || !rootRef.current) return;
    const els = gsap.utils.toArray<HTMLElement>(rootRef.current.querySelectorAll("[data-chrono-enter]"));
    if (!els.length) return;
    gsap.set(els, { opacity: 0, y: 26 });
    const tl = gsap.timeline({ defaults: { ease: "power2.out", duration: 0.65 } });
    els.forEach((el, index) => {
      tl.to(el, { opacity: 1, y: 0 }, index === 0 ? 0 : "+=0.14");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, { scope: rootRef, dependencies: [tier, style] });

  return (
    <div ref={rootRef} className={className}>
      {children}
    </div>
  );
}
