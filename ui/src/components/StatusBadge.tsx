export function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-all ${
        ok
          ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.15)]"
          : "bg-neutral-900/60 border-neutral-700/40 text-neutral-400"
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          ok ? "bg-emerald-400 animate-pulse" : "bg-neutral-500"
        }`}
      />
      {label}
    </span>
  );
}
