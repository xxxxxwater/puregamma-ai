export function SelectionBox({ selected }: { selected: boolean }) {
  return (
    <div className={`mt-1 flex h-5 w-5 shrink-0 items-center justify-center border ${selected ? "border-border-pg-strong bg-pg-white" : "border-border-pg"}`}>
      {selected ? <span className="text-xs text-pg-black">✓</span> : null}
    </div>
  );
}
