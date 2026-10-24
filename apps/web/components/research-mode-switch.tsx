"use client";

export function ResearchModeSwitch({
  enabled,
  onChange,
  labels,
}: {
  /** Research and connected modes use inverse monochrome treatments. */
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  labels: { on: string; off: string };
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={() => onChange(!enabled)}
      className={`inline-flex h-6 w-[4.25rem] shrink-0 cursor-pointer items-center justify-center rounded-full border px-1 text-[0.6rem] font-bold uppercase tracking-[0.12em] transition-colors duration-200 ${
        enabled
          ? "border-border-pg-strong bg-pg-white text-pg-black"
          : "border-border-pg-strong bg-pg-black text-pg-white"
      }`}
    >
      {enabled ? labels.on : labels.off}
    </button>
  );
}
