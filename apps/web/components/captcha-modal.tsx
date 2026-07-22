"use client";

import { useEffect } from "react";
import { Loader2, ShieldCheck, X } from "lucide-react";
import { PuzzleCaptcha, type CaptchaResult } from "@/components/puzzle-captcha";

export function CaptchaModal({
  open,
  busy,
  error,
  resetKey,
  onSolved,
  onClose,
  onRefresh,
  labels,
}: {
  open: boolean;
  /** True while the solved offset is being verified with the server (login/register request in flight). */
  busy: boolean;
  /** Captcha-specific failure shown inside the modal; page-level errors are rendered by the caller. */
  error: string;
  /** Bump to remount the slider with a fresh puzzle. */
  resetKey: number;
  onSolved: (result: CaptchaResult) => void;
  onClose: () => void;
  onRefresh: () => void;
  labels: { title: string; verifying: string; instruction: string; success: string; drag: string };
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={labels.title}
      onClick={onClose}
    >
      <div
        className="w-full max-w-[360px] space-y-4 border border-border-pg bg-bg-panel p-5 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-text-pg">
            <ShieldCheck className="h-4 w-4 text-text-pg-muted" />
            {labels.title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="close"
            className="text-text-pg-dim transition hover:text-text-pg"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {error ? (
          <p className="border border-border-pg bg-bg-panel-muted px-3 py-2 text-xs text-status-negative">{error}</p>
        ) : null}

        <PuzzleCaptcha
          key={resetKey}
          verified={null}
          disabled={busy}
          onSolved={onSolved}
          onReset={onRefresh}
          labels={{ instruction: labels.instruction, success: labels.success, drag: labels.drag }}
        />

        {busy ? (
          <p className="flex items-center gap-2 text-xs text-text-pg-muted">
            <Loader2 className="h-3 w-3 animate-spin" />
            {labels.verifying}
          </p>
        ) : null}
      </div>
    </div>
  );
}
