"use client";

import { useEffect, useRef } from "react";
import { useMotionTierReactive, usePageVisible, type MotionTier } from "@/lib/ocean";

type PointerEventLike = { clientX: number; clientY: number };

type Ripple = { x: number; y: number; radius: number; alpha: number; born: number };

const RIPPLE_LIFE_MS = 1100;
const MAX_RIPPLES = 4;

/**
 * Low-opacity flowing light layers for Agent / Research / Today surfaces.
 *
 * - Canvas 2D only; no WebGL, no third-party library.
 * - Pauses the rAF loop when the tab is hidden or unmounted.
 * - `static` tier renders a pure CSS gradient (reduced motion / phones).
 * - `light` tier draws fewer layers, no pointer glow, tap ripples only.
 * - Layer alpha stays within the 0.05 – 0.18 budget; never covers content.
 */
export function OceanBackground({ variant = "agent", forceStatic = false, className = "" }: { variant?: "agent" | "research"; forceStatic?: boolean; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const tier = useMotionTierReactive();
  const visible = usePageVisible();
  const effectiveTier = forceStatic ? "static" : tier;
  const tierRef = useRef<MotionTier>(effectiveTier);
  const visibleRef = useRef(visible);
  const variantRef = useRef(variant);
  tierRef.current = effectiveTier;
  visibleRef.current = visible;
  variantRef.current = variant;

  useEffect(() => {
    if (effectiveTier === "static") return;
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let raf = 0;
    let disposed = false;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
    };
    resize();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
    observer?.observe(wrap);

    const layerColors = [
      variantRef.current === "research" ? "46, 125, 255" : "46, 125, 255",
      "66, 217, 255",
      "139, 124, 255",
    ];
    const layerAlphas = [0.075, 0.055, 0.05];
    const layerCount = () => (tierRef.current === "light" ? 2 : 3);
    const start = performance.now();

    // Pointer glow (desktop full tier only) — soft halo, no trails.
    let glow: { x: number; y: number; targetX: number; targetY: number; intensity: number } | null = null;
    const onPointerMove = (event: PointerEventLike) => {
      const rect = wrap.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      if (!glow) glow = { x, y, targetX: x, targetY: y, intensity: 0 };
      glow.targetX = x;
      glow.targetY = y;
      glow.intensity = Math.min(1, glow.intensity + 0.06);
    };
    const onPointerLeave = () => {
      if (glow) glow.intensity = 0;
    };

    let ripples: Ripple[] = [];
    const spawnRipple = (event: PointerEventLike) => {
      const rect = wrap.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const size = tierRef.current === "light" ? 56 : 88;
      ripples = [...ripples.slice(-(MAX_RIPPLES - 1)), { x, y, radius: size, alpha: 0.5, born: performance.now() }];
    };

    const onPointerDown = (event: PointerEvent) => {
      if (event.pointerType === "mouse" && tierRef.current !== "full") return;
      spawnRipple(event);
    };

    const layers = (time: number) => {
      const count = layerCount();
      for (let index = 0; index < count; index += 1) {
        const cx = width * (0.18 + index * 0.36) + Math.sin(time * 0.00009 + index * 2.1) * width * 0.07;
        const cy = height * (0.22 + index * 0.24) + Math.cos(time * 0.00007 + index * 1.7) * height * 0.06;
        const radius = Math.max(width, height) * (0.5 + index * 0.14);
        const gradient = ctx!.createRadialGradient(cx, cy, 0, cx, cy, radius);
        gradient.addColorStop(0, `rgba(${layerColors[index]}, ${layerAlphas[index]})`);
        gradient.addColorStop(0.62, `rgba(${layerColors[index]}, ${layerAlphas[index] * 0.45})`);
        gradient.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx!.fillStyle = gradient;
        ctx!.fillRect(0, 0, width, height);
      }
    };

    const drawGlow = () => {
      if (!glow) return;
      glow.x += (glow.targetX - glow.x) * 0.08;
      glow.y += (glow.targetY - glow.y) * 0.08;
      glow.intensity = Math.max(0, glow.intensity - 0.002);
      if (glow.intensity <= 0.01) return;
      const gradient = ctx!.createRadialGradient(glow.x, glow.y, 0, glow.x, glow.y, 160);
      gradient.addColorStop(0, `rgba(66, 217, 255, ${0.10 * glow.intensity})`);
      gradient.addColorStop(1, "rgba(66, 217, 255, 0)");
      ctx!.fillStyle = gradient;
      ctx!.fillRect(0, 0, width, height);
    };

    const drawRipples = (time: number) => {
      ripples = ripples.filter((ripple) => time - ripple.born < RIPPLE_LIFE_MS);
      for (const ripple of ripples) {
        const progress = (time - ripple.born) / RIPPLE_LIFE_MS;
        const radius = ripple.radius * (0.2 + progress * 1.6);
        const alpha = ripple.alpha * (1 - progress);
        ctx!.strokeStyle = `rgba(66, 217, 255, ${alpha * 0.45})`;
        ctx!.lineWidth = 1;
        ctx!.beginPath();
        ctx!.arc(ripple.x, ripple.y, radius, 0, Math.PI * 2);
        ctx!.stroke();
      }
    };

    const frame = (time: number) => {
      if (disposed) return;
      raf = requestAnimationFrame(frame);
      const elapsed = time - start;
      const active = tierRef.current !== "static" && visibleRef.current;
      if (!active) return;
      ctx!.clearRect(0, 0, width, height);
      layers(elapsed);
      if (tierRef.current === "full") drawGlow();
      drawRipples(time);
    };

    raf = requestAnimationFrame(frame);
    wrap.addEventListener("pointermove", onPointerMove as unknown as EventListener);
    wrap.addEventListener("pointerleave", onPointerLeave);
    wrap.addEventListener("pointerdown", onPointerDown as unknown as EventListener);
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      observer?.disconnect();
      wrap.removeEventListener("pointermove", onPointerMove as unknown as EventListener);
      wrap.removeEventListener("pointerleave", onPointerLeave);
      wrap.removeEventListener("pointerdown", onPointerDown as unknown as EventListener);
    };
  }, [effectiveTier]);

  if (effectiveTier === "static") {
    return <div aria-hidden className={`ocean-static-gradient pointer-events-none absolute inset-0 ${className}`} />;
  }
  return (
    <div ref={wrapRef} aria-hidden className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
      <canvas ref={canvasRef} className="block h-full w-full" />
    </div>
  );
}
