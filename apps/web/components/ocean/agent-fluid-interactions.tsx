"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  type ButtonHTMLAttributes,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

const prefersReducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

function rubberBand(distance: number, dimension: number, constant = 0.55) {
  const value = Math.max(0, distance);
  return (1 - (1 / ((value * constant / Math.max(dimension, 1)) + 1))) * dimension;
}

type SpringOptions = {
  stiffness?: number;
  damping?: number;
  mass?: number;
  precision?: number;
};

type SpringState = { position: number; velocity: number };

/**
 * Stable spring integration that tracks wall-clock time without handing a huge
 * delta directly to Euler integration. When the main thread misses frames we
 * catch up using small fixed substeps, so motion does not enter slow motion
 * after jank while remaining numerically stable.
 */
function integrateSpring(
  position: number,
  velocity: number,
  target: number,
  stiffness: number,
  damping: number,
  mass: number,
  elapsedSeconds: number,
): SpringState {
  let x = position;
  let v = velocity;
  let remaining = Math.min(Math.max(elapsedSeconds, 1 / 240), 0.25);
  const maxStep = 1 / 120;

  while (remaining > 0.000001) {
    const dt = Math.min(maxStep, remaining);
    const acceleration = (-stiffness * (x - target) - damping * v) / mass;
    v += acceleration * dt;
    x += v * dt;
    remaining -= dt;
  }

  return { position: x, velocity: v };
}

/**
 * Drives a CSS custom property with a real second-order spring.
 * The current presentation value and velocity survive target changes, so an
 * interrupted collapse/expand reverses from exactly where it is instead of
 * restarting a scripted transition.
 */
export function useSpringCssVariable<T extends HTMLElement>(
  ref: RefObject<T>,
  variable: `--${string}`,
  target: number,
  initial: number,
  options: SpringOptions = {},
) {
  const positionRef = useRef(initial);
  const velocityRef = useRef(0);
  const frameRef = useRef<number | null>(null);
  const targetRef = useRef(target);
  const lastTimeRef = useRef(0);

  const stiffness = options.stiffness ?? 520;
  const damping = options.damping ?? 42;
  const mass = options.mass ?? 1;
  const precision = options.precision ?? 0.08;

  const apply = useCallback((value: number) => {
    ref.current?.style.setProperty(variable, `${value.toFixed(3)}px`);
  }, [ref, variable]);

  const step = useCallback((time: number) => {
    const node = ref.current;
    if (!node) {
      frameRef.current = null;
      return;
    }
    const previous = lastTimeRef.current || time;
    const elapsed = (time - previous) / 1000;
    lastTimeRef.current = time;

    const next = integrateSpring(
      positionRef.current,
      velocityRef.current,
      targetRef.current,
      stiffness,
      damping,
      mass,
      elapsed,
    );

    positionRef.current = next.position;
    velocityRef.current = next.velocity;
    apply(next.position);

    if (Math.abs(next.velocity) <= precision && Math.abs(next.position - targetRef.current) <= precision) {
      positionRef.current = targetRef.current;
      velocityRef.current = 0;
      apply(targetRef.current);
      frameRef.current = null;
      return;
    }
    frameRef.current = window.requestAnimationFrame(step);
  }, [apply, damping, mass, precision, ref, stiffness]);

  useLayoutEffect(() => {
    positionRef.current = initial;
    targetRef.current = initial;
    apply(initial);
    return () => {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      lastTimeRef.current = 0;
    };
  }, [apply, initial]);

  useEffect(() => {
    targetRef.current = target;
    if (prefersReducedMotion()) {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      velocityRef.current = 0;
      positionRef.current = target;
      apply(target);
      return;
    }
    if (frameRef.current === null) {
      lastTimeRef.current = performance.now();
      frameRef.current = window.requestAnimationFrame(step);
    }
  }, [apply, step, target]);
}

type SwipeSheetOptions = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  width?: number;
};

/** Left-side sheet with 1:1 tracking, pointer capture, velocity history,
 * momentum projection, rubber-banding and spring completion. */
export function useSwipeSheet({ open, onOpenChange, width = 320 }: SwipeSheetOptions) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLButtonElement>(null);
  const positionRef = useRef(open ? 0 : -width);
  const velocityRef = useRef(0);
  const frameRef = useRef<number | null>(null);
  const lastFrameRef = useRef(0);
  const targetRef = useRef(open ? 0 : -width);
  const gestureRef = useRef<{
    pointerId: number;
    startX: number;
    startPosition: number;
    samples: Array<{ x: number; time: number }>;
  } | null>(null);

  const apply = useCallback((position: number) => {
    positionRef.current = position;
    const progress = clamp(1 + position / width, 0, 1);
    if (sheetRef.current) {
      sheetRef.current.style.transform = `translate3d(${position.toFixed(2)}px,0,0)`;
      sheetRef.current.style.setProperty("--agent-sheet-progress", progress.toFixed(4));
    }
    if (backdropRef.current) backdropRef.current.style.opacity = String(progress * 0.62);
  }, [width]);

  const springStep = useCallback((time: number) => {
    const previous = lastFrameRef.current || time;
    const elapsed = (time - previous) / 1000;
    lastFrameRef.current = time;
    const next = integrateSpring(positionRef.current, velocityRef.current, targetRef.current, 560, 46, 1, elapsed);
    velocityRef.current = next.velocity;
    apply(next.position);
    if (Math.abs(next.velocity) < 1.2 && Math.abs(next.position - targetRef.current) < 0.35) {
      velocityRef.current = 0;
      apply(targetRef.current);
      frameRef.current = null;
      return;
    }
    frameRef.current = window.requestAnimationFrame(springStep);
  }, [apply]);

  const springTo = useCallback((target: number, initialVelocity = velocityRef.current) => {
    targetRef.current = target;
    velocityRef.current = initialVelocity;
    if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    if (prefersReducedMotion()) {
      velocityRef.current = 0;
      apply(target);
      return;
    }
    lastFrameRef.current = performance.now();
    frameRef.current = window.requestAnimationFrame(springStep);
  }, [apply, springStep]);

  useLayoutEffect(() => {
    apply(open ? 0 : -width);
    return () => {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      lastFrameRef.current = 0;
    };
  }, [apply, width]);

  useEffect(() => {
    if (gestureRef.current) return;
    springTo(open ? 0 : -width);
  }, [open, springTo, width]);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [open]);

  const finishGesture = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const samples = gesture.samples;
    const recent = samples.filter((sample) => performance.now() - sample.time <= 120);
    const first = recent[0] ?? samples[0];
    const last = recent[recent.length - 1] ?? samples[samples.length - 1];
    const elapsed = Math.max(last.time - first.time, 1);
    const velocity = ((last.x - first.x) / elapsed) * 1000;
    velocityRef.current = velocity;
    gestureRef.current = null;
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch { /* capture already released */ }

    // Project 180ms into the future. Fast flicks therefore carry their intent
    // even when the travelled distance is short.
    const projected = positionRef.current + velocity * 0.18;
    const shouldOpen = projected > -width * 0.42;
    springTo(shouldOpen ? 0 : -width, velocity);
    onOpenChange(shouldOpen);
  }, [onOpenChange, springTo, width]);

  const bind = {
    onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => {
      if (!event.isPrimary || event.button !== 0) return;
      const target = event.target as HTMLElement;
      if (target.closest("button,a,input,select,textarea,[role='button']")) return;
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      event.currentTarget.setPointerCapture(event.pointerId);
      const now = performance.now();
      gestureRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startPosition: positionRef.current,
        samples: [{ x: event.clientX, time: now }],
      };
    },
    onPointerMove: (event: ReactPointerEvent<HTMLDivElement>) => {
      const gesture = gestureRef.current;
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      const raw = gesture.startPosition + event.clientX - gesture.startX;
      let tracked = raw;
      if (raw > 0) tracked = rubberBand(raw, width);
      else if (raw < -width) tracked = -width - rubberBand(-width - raw, width);
      apply(tracked);
      const now = performance.now();
      gesture.samples.push({ x: event.clientX, time: now });
      if (gesture.samples.length > 8) gesture.samples.shift();
    },
    onPointerUp: finishGesture,
    onPointerCancel: finishGesture,
  };

  return { sheetRef, backdropRef, bind, springTo };
}

type FluidPressButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  pressScale?: number;
};

/**
 * Small physical button: immediate down-state, ~10px hysteresis, direct pointer
 * tracking, then a spring return that receives the pointer's release velocity.
 */
export function FluidPressButton({ children, className = "", disabled, pressScale = 0.955, onPointerDown, onPointerMove, onPointerUp, onPointerCancel, onClick, ...props }: FluidPressButtonProps) {
  const ref = useRef<HTMLButtonElement>(null);
  const frameRef = useRef<number | null>(null);
  const xRef = useRef(0);
  const yRef = useRef(0);
  const vxRef = useRef(0);
  const vyRef = useRef(0);
  const lastFrameRef = useRef(0);
  const suppressClickRef = useRef(false);
  const gestureRef = useRef<{ pointerId: number; startX: number; startY: number; samples: Array<{ x: number; y: number; time: number }> } | null>(null);

  const apply = useCallback((x: number, y: number, scale: number) => {
    xRef.current = x;
    yRef.current = y;
    if (ref.current) ref.current.style.transform = `translate3d(${x.toFixed(2)}px,${y.toFixed(2)}px,0) scale(${scale.toFixed(4)})`;
  }, []);

  const springStep = useCallback((time: number) => {
    const previous = lastFrameRef.current || time;
    const elapsed = (time - previous) / 1000;
    lastFrameRef.current = time;
    const xSpring = integrateSpring(xRef.current, vxRef.current, 0, 620, 44, 1, elapsed);
    const ySpring = integrateSpring(yRef.current, vyRef.current, 0, 620, 44, 1, elapsed);
    vxRef.current = xSpring.velocity;
    vyRef.current = ySpring.velocity;
    const distance = Math.hypot(xSpring.position, ySpring.position);
    const scale = 1 - Math.min(distance / 90, 0.018);
    apply(xSpring.position, ySpring.position, scale);
    if (Math.abs(vxRef.current) < 0.35 && Math.abs(vyRef.current) < 0.35 && distance < 0.08) {
      vxRef.current = 0;
      vyRef.current = 0;
      apply(0, 0, 1);
      frameRef.current = null;
      return;
    }
    frameRef.current = window.requestAnimationFrame(springStep);
  }, [apply]);

  const release = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const first = gesture.samples[0];
    const last = gesture.samples[gesture.samples.length - 1];
    const elapsed = Math.max(last.time - first.time, 1);
    const pointerVx = ((last.x - first.x) / elapsed) * 1000;
    const pointerVy = ((last.y - first.y) / elapsed) * 1000;
    vxRef.current = pointerVx * 0.018;
    vyRef.current = pointerVy * 0.018;
    suppressClickRef.current = Math.hypot(last.x - gesture.startX, last.y - gesture.startY) > 10;
    gestureRef.current = null;
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch { /* capture already released */ }
    if (prefersReducedMotion()) {
      apply(0, 0, 1);
      return;
    }
    if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
    lastFrameRef.current = performance.now();
    frameRef.current = window.requestAnimationFrame(springStep);
  }, [apply, springStep]);

  useEffect(() => () => {
    if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    lastFrameRef.current = 0;
  }, []);

  return (
    <button
      ref={ref}
      disabled={disabled}
      className={`agent-fluid-press ${className}`}
      onPointerDown={(event) => {
        onPointerDown?.(event);
        if (event.defaultPrevented || disabled || !event.isPrimary || event.button !== 0) return;
        if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
        event.currentTarget.setPointerCapture(event.pointerId);
        const now = performance.now();
        gestureRef.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, samples: [{ x: event.clientX, y: event.clientY, time: now }] };
        apply(0, 0.5, prefersReducedMotion() ? 1 : pressScale);
      }}
      onPointerMove={(event) => {
        onPointerMove?.(event);
        const gesture = gestureRef.current;
        if (!gesture || gesture.pointerId !== event.pointerId || disabled) return;
        const dx = clamp((event.clientX - gesture.startX) * 0.075, -1.8, 1.8);
        const dy = clamp((event.clientY - gesture.startY) * 0.075 + 0.5, -1.4, 2.1);
        apply(dx, dy, prefersReducedMotion() ? 1 : pressScale);
        const now = performance.now();
        gesture.samples.push({ x: event.clientX, y: event.clientY, time: now });
        if (gesture.samples.length > 7) gesture.samples.shift();
      }}
      onPointerUp={(event) => { onPointerUp?.(event); release(event); }}
      onPointerCancel={(event) => { onPointerCancel?.(event); release(event); }}
      onClick={(event) => {
        if (suppressClickRef.current) {
          suppressClickRef.current = false;
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </button>
  );
}
