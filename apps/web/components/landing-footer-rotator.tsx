"use client";

import { useEffect, useRef, useState } from "react";

const ROTATE_INTERVAL_MS = 4500;
const FADE_MS = 300;

export function LandingFooterRotator({ slides }: { slides: string[] }) {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);
  const fadeTimer = useRef<number | null>(null);

  useEffect(() => {
    if (slides.length < 2) {
      return;
    }
    const interval = window.setInterval(() => {
      setVisible(false);
      fadeTimer.current = window.setTimeout(() => {
        setIndex((current) => (current + 1) % slides.length);
        setVisible(true);
      }, FADE_MS);
    }, ROTATE_INTERVAL_MS);
    return () => {
      window.clearInterval(interval);
      if (fadeTimer.current !== null) {
        window.clearTimeout(fadeTimer.current);
      }
    };
  }, [slides.length]);

  return (
    <footer className="border-t border-border-pg pt-5 text-xs text-text-pg-muted" aria-live="polite">
      <span className={`block transition-opacity duration-300 ${visible ? "opacity-100" : "opacity-0"}`}>
        {slides[index] ?? ""}
      </span>
      {slides.length > 1 ? (
        <span className="mt-2 flex gap-1.5" aria-hidden="true">
          {slides.map((slide, slideIndex) => (
            <span
              key={slide}
              className={`h-0.5 w-5 transition-colors duration-300 ${slideIndex === index ? "bg-text-pg-muted" : "bg-border-pg"}`}
            />
          ))}
        </span>
      ) : null}
    </footer>
  );
}
