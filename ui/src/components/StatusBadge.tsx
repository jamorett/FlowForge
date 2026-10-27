export function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`inline-block px-2 py-0.5 text-xs border ${ok ? "border-emerald-700 text-emerald-800" : "border-neutral-400 text-neutral-500"}`}>{label}</span>;
}
