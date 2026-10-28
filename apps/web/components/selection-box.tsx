export function SelectionBox({ selected }: { selected: boolean }) {
  return (
    <div className={`mt-1 flex h-5 w-5 shrink-0 items-center justify-center border  rounded-lg ${selected ? "border-border-pg-strong bg-[var(--pg-surface-inverse)]" : "border-border-pg"}`}>
      {selected ? <span className="text-xs text-[var(--pg-text-inverse)]">✓</span> : null}
    </div>
  );
}
