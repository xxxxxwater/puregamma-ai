"use client";

import { useRef, type ReactNode } from "react";
import { gsap, useGSAP } from "@/components/chrono/motion";
import { useChronoTierReactive, useHtmlDataset } from "@/lib/chrono";

/**
 * The scarce, expensive liquid-glass surface. Real backdrop blur, 1px
 * refractive top edge, multi-layer fill and a pointer-driven sheen that
 * moves the CSS vars --lx/--ly (cheap custom-prop updates via quickTo).
 * Glass + full tier + desktop only; everything else renders a calm solid.
 */
export function LiquidLens({ children, className = "", as: Tag = "div" }: { children: ReactNode; className?: string; as?: "div" | "section" }) {
  const ref = useRef<HTMLElement | null>(null);
  const tier = useChronoTierReactive();
  const style = useHtmlDataset("visualStyle");

  useGSAP(() => {
    if (style === "classic" || tier !== "full") return;
    const el = ref.current;
    if (!el) return;
    const state = { x: 50, y: -12 };
    el.style.setProperty("--lx", state.x + "%");
    el.style.setProperty("--ly", state.y + "%");
    const xTo = gsap.quickTo(state, "x", { duration: 0.55, ease: "power2.out", onUpdate: () => el.style.setProperty("--lx", state.x + "%") });
    const yTo = gsap.quickTo(state, "y", { duration: 0.55, ease: "power2.out", onUpdate: () => el.style.setProperty("--ly", state.y + "%") });
    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      const rect = el.getBoundingClientRect();
      xTo(((event.clientX - rect.left) / Math.max(1, rect.width)) * 100);
      yTo(((event.clientY - rect.top) / Math.max(1, rect.height)) * 100);
    };
    const onLeave = () => { xTo(50); yTo(-12); };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, { scope: ref, dependencies: [tier, style] });

  return (
    <Tag ref={ref as never} className={"liquid " + className}>
      {children}
    </Tag>
  );
}
