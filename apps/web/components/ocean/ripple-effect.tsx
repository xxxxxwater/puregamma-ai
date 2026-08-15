"use client";

import { useCallback, useRef, type PointerEvent, type ReactNode } from "react";
import { resolveMotionTier } from "@/lib/ocean";

/**
 * Localized tap/click ripple for Agent / Research interactions only:
 * agent composer, research run cards, evidence nodes.
 * NEVER use on trading order, confirm, or risk action buttons.
 */
export function RippleEffect({ children, className = "", as: Tag = "div", type, disabled, onClick, ariaLabel }: {
  children: ReactNode;
  className?: string;
  as?: "div" | "button";
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: () => void;
  ariaLabel?: string;
}) {
  const tier = resolveMotionTier();
  const containerRef = useRef<HTMLElement | null>(null);
  const setRef = useCallback((node: HTMLElement | null) => {
    containerRef.current = node;
  }, []);

  const spawn = useCallback((event: PointerEvent) => {
    if (disabled || tier === "static") return;
    if (event.pointerType && event.pointerType !== "mouse" && event.pointerType !== "touch" && event.pointerType !== "pen") return;
    const node = containerRef.current;
    if (!node) return;
    const rect = node.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const size = Math.min(rect.width, rect.height) * 0.9;
    const span = document.createElement("span");
    span.className = "ocean-ripple-ring";
    span.style.left = `${x - size / 2}px`;
    span.style.top = `${y - size / 2}px`;
    span.style.width = `${size}px`;
    span.style.height = `${size}px`;
    node.appendChild(span);
    span.addEventListener("animationend", () => span.remove(), { once: true });
    // Safety net in case the animation never fires (e.g. paused tab).
    window.setTimeout(() => span.remove(), 1400);
  }, [tier, disabled]);

  return (
    <Tag
      ref={setRef}
      className={`relative overflow-hidden ${className}`}
      onPointerDown={spawn}
      onClick={onClick}
      aria-label={ariaLabel}
      {...(Tag === "button" ? { type, disabled } : {})}
    >
      {children}
    </Tag>
  );
}
