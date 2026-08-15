"use client";

import { useState, type ReactNode } from "react";
import { Waves, WavesLadder } from "lucide-react";
import { OceanBackground } from "@/components/ocean/ocean-background";
import { PointerGlow } from "@/components/ocean/pointer-glow";
import { storeTier, useMotionTierReactive } from "@/lib/ocean";

/**
 * Outer shell for Agent / Research / Today exploration surfaces.
 *
 * Provides the deep intelligent backdrop, a content safe-area that always
 * stays above the layers, and a discreet performance-degrade control.
 * Financial surfaces (Portfolio / NAV / Trading / Trading Safety) must not
 * use this component.
 */
export function OceanShell({ locale, variant = "agent", className = "", children, degradeControl = true }: {
  locale: "en" | "zh";
  variant?: "agent" | "research";
  className?: string;
  children: ReactNode;
  degradeControl?: boolean;
}) {
  const zh = locale === "zh";
  const tier = useMotionTierReactive();
  const [forcedStatic, setForcedStatic] = useState(false);
  const staticNow = tier === "static" || forcedStatic;
  // Agent keeps a thin luminous frame around its solid work panel so the
  // ocean stays visible without ever sitting behind body text.
  const frame = variant === "agent";
  // Degrade control only makes sense when a dynamic background can exist.
  // Derived from the reactive hook so server/client first renders match.
  const canDegrade = tier !== "static";

  const toggleDegrade = () => {
    const next = staticNow ? null : "static";
    storeTier(next);
    setForcedStatic(next === "static");
  };

  return (
    <div className={`relative overflow-hidden border border-border-pg ${className}`}>
      <OceanBackground variant={variant} forceStatic={staticNow} />
      <PointerGlow />
      <div className={`relative z-10 h-full min-h-full ${frame ? "p-1 md:p-1.5" : ""}`}>{children}</div>
      {degradeControl && canDegrade ? (
        <button
          type="button"
          onClick={toggleDegrade}
          aria-pressed={staticNow}
          title={zh ? (staticNow ? "恢复动态背景" : "关闭动态背景（降低性能消耗）") : staticNow ? "Re-enable dynamic background" : "Disable dynamic background (performance)"}
          className="absolute right-2 top-2 z-20 flex items-center gap-1.5 border border-border-pg bg-bg-panel px-2 py-1 text-[10px] text-text-pg-dim opacity-70 transition hover:opacity-100 hover:border-border-pg-strong rounded-lg"
        >
          {staticNow ? <WavesLadder className="h-3 w-3" /> : <Waves className="h-3 w-3" />}
          {staticNow ? (zh ? "已静止" : "Static") : (zh ? "动态" : "Motion")}
        </button>
      ) : null}
    </div>
  );
}
