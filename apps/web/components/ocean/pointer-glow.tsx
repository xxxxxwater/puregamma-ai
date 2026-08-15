"use client";

import { useEffect, useRef } from "react";
import { useMotionTierReactive, usePageVisible } from "@/lib/ocean";

/**
 * Desktop-only low-intensity cursor halo for Agent / Research surfaces.
 * Mobile never renders it; tap feedback is handled by OceanBackground ripples.
 */
export function PointerGlow() {
  const ref = useRef<HTMLDivElement | null>(null);
  const tier = useMotionTierReactive();
  const visible = usePageVisible();
  const visibleRef = useRef(visible);
  visibleRef.current = visible;

  useEffect(() => {
    if (tier !== "full") return;
    const node = ref.current;
    if (!node) return;
    let raf = 0;
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;
    let opacity = 0;

    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      targetX = event.clientX;
      targetY = event.clientY;
      opacity = 1;
      node.style.opacity = "1";
    };
    const onLeave = () => {
      opacity = 0;
    };

    const frame = () => {
      raf = requestAnimationFrame(frame);
      currentX += (targetX - currentX) * 0.06;
      currentY += (targetY - currentY) * 0.06;
      opacity = Math.max(0, opacity - 0.015);
      if (!visibleRef.current) return;
      node.style.transform = `translate3d(${currentX - 140}px, ${currentY - 140}px, 0)`;
      node.style.opacity = String(Math.min(1, opacity));
    };
    raf = requestAnimationFrame(frame);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerleave", onLeave);
    };
  }, [tier]);

  if (tier !== "full") return null;
  return (
    <div
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed left-0 top-0 z-0 h-[280px] w-[280px] opacity-0"
      style={{ background: "radial-gradient(circle, rgba(66, 217, 255, 0.07) 0%, rgba(46, 125, 255, 0.05) 42%, transparent 68%)" }}
    />
  );
}
