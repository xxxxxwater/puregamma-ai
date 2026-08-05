"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { getCaptchaPuzzle } from "@/lib/api";

type Puzzle = {
  captcha_id: string;
  background: string;
  piece: string;
  piece_y: number;
  width: number;
  height: number;
};

export type CaptchaResult = { captchaId: string; offset: number };

const TRACK_WIDTH = 320;
const PIECE_SIZE = 42;
const SOLVE_TOLERANCE = 12;

export function PuzzleCaptcha({
  verified,
  disabled = false,
  onSolved,
  onReset,
  labels,
  retryToken = 0,
}: {
  verified: CaptchaResult | null;
  disabled?: boolean;
  onSolved: (result: CaptchaResult) => void;
  onReset: () => void;
  labels: { instruction: string; success: string; drag: string };
  /** Bump to allow another attempt with the SAME puzzle (slider resets, puzzle stays). */
  retryToken?: number;
}) {
  const [puzzle, setPuzzle] = useState<Puzzle | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragX, setDragX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const startX = useRef(0);
  const solvedRef = useRef(false);
  const trackRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setDragX(0);
    solvedRef.current = false;
    try {
      setPuzzle(await getCaptchaPuzzle());
    } catch {
      setPuzzle(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Server rejected the attempt but kept the puzzle alive: reset the slider and
  // let the user try again without fetching a new challenge.
  useEffect(() => {
    if (retryToken > 0) {
      solvedRef.current = false;
      setDragX(0);
    }
  }, [retryToken]);

  const maxDrag = TRACK_WIDTH - PIECE_SIZE - 8;

  const finishDrag = useCallback(() => {
    if (!puzzle || solvedRef.current) return;
    setDragging(false);
    // Convert track px to SVG coordinates: the piece starts at x=8 in a 320-wide viewBox.
    const offset = Math.round(8 + dragX);
    if (verified) return;
    onSolved({ captchaId: puzzle.captcha_id, offset });
    solvedRef.current = true;
  }, [dragX, onSolved, puzzle, verified]);

  const onPointerDown = (event: React.PointerEvent) => {
    if (!puzzle || verified || disabled) return;
    setDragging(true);
    startX.current = event.clientX - dragX;
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent) => {
    if (!dragging || verified || disabled) return;
    setDragX(Math.max(0, Math.min(maxDrag, event.clientX - startX.current)));
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[11px] text-text-pg-dim">
        <span>{labels.instruction}</span>
        <button type="button" disabled={disabled} onClick={() => { onReset(); void load(); }} className="inline-flex items-center gap-1 text-text-pg-muted transition hover:text-text-pg disabled:cursor-not-allowed disabled:opacity-50" aria-label="refresh captcha">
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>
      <div ref={trackRef} className="relative select-none overflow-hidden border border-border-pg" style={{ width: TRACK_WIDTH, maxWidth: "100%" }}>
        {loading || !puzzle ? (
          <div className="grid h-[120px] place-items-center bg-bg-panel-muted"><Loader2 className="h-5 w-5 animate-spin text-text-pg-dim" /></div>
        ) : (
          <>
            <img src={puzzle.background} width={TRACK_WIDTH} height={puzzle.height} alt="" draggable={false} className="block" />
            <img
              src={puzzle.piece}
              width={PIECE_SIZE}
              height={PIECE_SIZE}
              alt=""
              draggable={false}
              className="pointer-events-none absolute top-0"
              style={{ left: 8 + dragX, top: puzzle.piece_y, filter: "drop-shadow(0 1px 3px rgba(0,0,0,0.5))" }}
            />
          </>
        )}
      </div>
      <div
        role="slider"
        aria-valuemin={0}
        aria-valuemax={maxDrag}
        aria-valuenow={Math.round(dragX)}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
        onKeyDown={(event) => {
          if (verified || !puzzle || disabled) return;
          if (event.key === "ArrowRight") setDragX((value) => Math.min(maxDrag, value + 8));
          if (event.key === "ArrowLeft") setDragX((value) => Math.max(0, value - 8));
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            finishDrag();
          }
        }}
        className={`relative h-9 border text-[11px] ${disabled ? "cursor-wait opacity-70" : "cursor-ew-resize"} ${verified ? "border-status-positive bg-bg-panel-muted text-status-positive" : "border-border-pg bg-bg-panel-muted text-text-pg-dim"}`}
      >
        <div className={`absolute inset-y-0 left-0 ${verified ? "bg-status-positive/20" : "bg-border-pg"}`} style={{ width: 30 + dragX }} />
        <div
          className={`absolute top-1/2 grid h-7 w-10 -translate-y-1/2 place-items-center border font-semibold ${verified ? "border-status-positive bg-status-positive/20" : "border-border-pg-strong bg-bg-panel"}`}
          style={{ left: dragX }}
        >
          ⇢
        </div>
        <span className="pointer-events-none absolute inset-0 grid place-items-center">{verified ? labels.success : labels.drag}</span>
      </div>
    </div>
  );
}
