"use client";

import { useRef, useState } from "react";
import { FluidPressButton, useSpringCssVariable, useSwipeSheet } from "@/components/ocean/agent-fluid-interactions";

/**
 * Isolated QA harness for the Agent physical interaction primitives.
 * The route that renders this component is disabled unless ENABLE_QA_SURFACES=true.
 * It intentionally has no auth, API, market-data, or SSE dependencies so CI can
 * exercise the interaction physics deterministically in Chromium and WebKit.
 */
export function AgentFluidQa() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pressCount, setPressCount] = useState(0);
  const gridRef = useRef<HTMLDivElement>(null);

  useSpringCssVariable(gridRef, "--agent-history-width", collapsed ? 52 : 244, 244, {
    stiffness: 500,
    damping: 40,
    mass: 1,
  });
  const mobileSheet = useSwipeSheet({ open: mobileOpen, onOpenChange: setMobileOpen, width: 320 });

  return (
    <main className="apple-agent-workspace min-h-screen bg-bg-app p-6 text-text-pg">
      <div className="mx-auto max-w-5xl space-y-8">
        <header>
          <div className="text-xs uppercase tracking-[0.14em] text-text-pg-dim">PureGamma · QA only</div>
          <h1 className="mt-2 text-2xl font-semibold">Agent Fluid Interaction Harness</h1>
          <p className="mt-2 max-w-2xl text-sm text-text-pg-muted">No backend calls. This surface exists only when ENABLE_QA_SURFACES=true.</p>
        </header>

        <section>
          <div className="mb-3 flex items-center gap-3">
            <FluidPressButton data-testid="toggle-history" type="button" onClick={() => setCollapsed((value) => !value)} className="rounded-xl border border-border-pg px-3 py-2 text-xs">
              Toggle history
            </FluidPressButton>
            <span className="text-xs text-text-pg-dim">Interrupt this repeatedly to verify velocity-preserving reversal.</span>
          </div>
          <div ref={gridRef} data-testid="history-grid" className="agent-shell-grid grid h-64 overflow-hidden rounded-2xl border border-border-pg bg-bg-panel">
            <aside className="agent-desktop-history min-w-0 overflow-hidden border-r border-border-pg bg-bg-app">
              <div className="min-w-[244px] p-4 text-sm">Conversation history</div>
            </aside>
            <div className="min-w-0 p-4 text-sm text-text-pg-muted">Workspace remains spatially stable while the rail springs.</div>
          </div>
        </section>

        <section className="grid gap-6 md:grid-cols-2">
          <div>
            <div className="mb-3 text-xs uppercase tracking-[0.12em] text-text-pg-dim">Composer pressure</div>
            <div className="agent-composer flex max-w-md items-end gap-2 rounded-2xl border border-border-pg bg-bg-panel p-2">
              <textarea aria-label="QA composer" defaultValue="Drag the send control while pressed." rows={2} className="agent-composer-input min-h-14 flex-1 resize-none bg-transparent px-3 py-2 text-sm outline-none" />
              <FluidPressButton data-testid="fluid-press" type="button" onClick={() => setPressCount((count) => count + 1)} className="agent-composer-action agent-composer-send grid h-12 w-12 place-items-center rounded-xl border border-border-pg-strong bg-pg-white text-pg-black">
                ↑
              </FluidPressButton>
            </div>
            <div data-testid="press-count" className="mt-2 text-xs text-text-pg-dim">clicks:{pressCount}</div>
          </div>

          <div className="relative min-h-56 overflow-visible">
            <div className="mb-3 text-xs uppercase tracking-[0.12em] text-text-pg-dim">Anchored settings</div>
            <div className="agent-settings-anchor max-w-md">
              <FluidPressButton data-testid="settings-trigger" type="button" aria-expanded={settingsOpen} onClick={() => setSettingsOpen((value) => !value)} className="agent-settings-trigger flex w-full items-center justify-between rounded-2xl border border-border-pg bg-bg-panel p-3 text-xs">
                Advanced research settings <span>{settingsOpen ? "▲" : "▼"}</span>
              </FluidPressButton>
              {settingsOpen ? (
                <div data-testid="settings-sheet" role="dialog" className="agent-settings-sheet">
                  <div className="agent-settings-sheet-head"><span>Research context</span><span className="text-text-pg-dim">Auto</span></div>
                  <div className="agent-settings-sheet-body text-xs text-text-pg-muted">The sheet is anchored above its trigger and does not reflow the composer.</div>
                  <div className="agent-settings-sheet-foot"><span>Esc / click trigger to close</span></div>
                </div>
              ) : null}
            </div>
          </div>
        </section>

        <section>
          <div className="mb-3 text-xs uppercase tracking-[0.12em] text-text-pg-dim">Streaming state</div>
          <div data-testid="streaming-message" aria-busy="true" className="agent-message agent-message-assistant is-streaming max-w-2xl border-l border-border-pg pl-4">
            <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wide text-text-pg-dim">GPT-5.6 Sol <span className="agent-stream-live"><span aria-hidden />Live</span></div>
            <p className="text-sm leading-6">A subtle live rail and dot communicate activity without turning the answer into a loading animation.</p>
          </div>
        </section>

        <section>
          <FluidPressButton data-testid="open-mobile-history" type="button" onClick={() => setMobileOpen(true)} className="rounded-xl border border-border-pg px-3 py-2 text-xs">Open mobile history sheet</FluidPressButton>
          <button ref={mobileSheet.backdropRef} type="button" aria-label="Close QA history" onClick={() => setMobileOpen(false)} className={`agent-mobile-history-backdrop ${mobileOpen ? "is-open" : ""}`} />
          <div ref={mobileSheet.sheetRef} data-testid="mobile-sheet" className={`agent-mobile-history-sheet ${mobileOpen ? "is-open" : ""}`} role="dialog" aria-modal="true" aria-label="QA conversation history">
            <div data-testid="mobile-grab" className="agent-mobile-history-grab" {...mobileSheet.bind}>
              <span aria-hidden />
              <div className="flex-1 text-sm">Drag this header left and release.</div>
              <FluidPressButton type="button" onClick={() => setMobileOpen(false)} className="grid h-9 w-9 place-items-center rounded-xl border border-border-pg">×</FluidPressButton>
            </div>
            <div className="p-4 text-sm text-text-pg-muted">Velocity history + momentum projection + rubber band + spring completion.</div>
          </div>
        </section>
      </div>
    </main>
  );
}
