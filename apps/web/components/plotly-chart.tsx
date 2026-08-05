"use client";

import { useEffect, useRef } from "react";

declare global {
  interface Window {
    Plotly?: { newPlot: (el: HTMLElement, data: unknown[], layout?: unknown, config?: unknown) => Promise<unknown>; purge: (el: HTMLElement) => void };
  }
}

export function PlotlyChart({ figure, className = "h-72" }: { figure: { data?: unknown[]; layout?: Record<string, unknown> }; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    const element = ref.current;
    const render = async () => {
      if (!element || !window.Plotly || cancelled) return;
      await window.Plotly.newPlot(element, figure.data || [], { autosize: true, margin: { t: 36, r: 16, b: 42, l: 52 }, ...(figure.layout || {}) }, { responsive: true, displaylogo: false });
    };
    render();
    const timer = window.setInterval(() => { if (window.Plotly) { render(); window.clearInterval(timer); } }, 250);
    const timeout = window.setTimeout(() => window.clearInterval(timer), 5000);
    return () => { cancelled = true; window.clearInterval(timer); window.clearTimeout(timeout); if (element && window.Plotly) window.Plotly.purge(element); };
  }, [figure]);
  return <div ref={ref} className={className} data-plotly-chart />;
}
