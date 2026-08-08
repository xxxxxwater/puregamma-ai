"use client";

export function ResearchModeSwitch({
  enabled,
  onChange,
  labels,
}: {
  /** true = research mode ON (white "ON"); false = 联网模式 (blue "OFF"). */
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
          : "border-transparent bg-[#0A84FF] text-pg-white"
      }`}
    >
      {enabled ? labels.on : labels.off}
    </button>
  );
}
