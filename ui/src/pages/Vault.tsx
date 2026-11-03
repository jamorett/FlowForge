import { useQuery } from "@tanstack/react-query";
import { fetchVault, type VaultEval } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";

/** One candidate per row with its ratio on each locked case (direct-set) or the single champion (direct). */
function rows(e: VaultEval): { name: string; expr: string; cases: Record<string, number> }[] {
  const one = (name: string, r: any) => ({ name, expr: r?.champion ?? "", cases: Object.fromEntries(
    Object.entries(r?.cases ?? {}).map(([c, m]: [string, any]) => [c, m?.error_ratio])) });
  if (e.scores?.candidates) return Object.entries(e.scores.candidates).map(([n, r]) => one(n, r));
  return e.scores?.cases ? [one("champion", e.scores)] : [];
}

export function Vault() {
  const q = useQuery({ queryKey: ["vault"], queryFn: fetchVault, refetchInterval: 15000 });
  const evals = q.data?.evaluations ?? [];
  const scoredAt = (c: string) => evals.find((e) => rows(e).some((r) => c in r.cases))?.milestone;
  return (
    <section aria-label="Locked Test Vault" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <span>🔒</span>
            <span>Locked Test Data Vault</span>
          </h2>
          <p className="text-xs text-neutral-400 mt-1">
            Strict isolation guardrail: held-out cases are isolated from the agent swarm to prevent data snooping.
          </p>
        </div>
        <StatusBadge ok={true} label="Vault Armed & Isolated" />
      </div>

      {/* Vault Guardrail Banner */}
      <div className="glass-panel p-5 rounded-xl border border-rose-500/30 bg-rose-950/20 space-y-2">
        <div className="flex items-center gap-2 text-rose-300 font-semibold text-sm">
          <span>⚠️</span>
          <span>Scientific Evaluation Discipline (Section S7.2)</span>
        </div>
        <p className="text-xs text-neutral-300 leading-relaxed">
          The directory <code className="text-rose-300 font-mono">data/locked/</code> is guarded by{" "}
          <code className="text-rose-300 font-mono">split_guard.py</code>. Swarm agents and tools are forbidden from reading locked cases. Locked evaluation may occur{" "}
          <strong className="text-white">at most 3 times</strong> across the entire research campaign: Milestone 1, Milestone 2, and Final Champion Submission.
        </p>
      </div>

      {/* Locked Cases Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-panel p-4 rounded-xl border border-white/10 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-neutral-200">square_duct</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-neutral-800 text-neutral-400 font-mono">
              Re_tau = 2205
            </span>
          </div>
          <p className="text-xs text-neutral-400">
            Prandtl secondary motion of the second kind. Non-circular cross-section test for Reynolds stress anisotropy.
          </p>
          <div className="pt-2 flex items-center gap-2 text-[11px] text-neutral-500">
            <span>Status:</span>
            <span className={scoredAt("square_duct") ? "text-emerald-400 font-medium" : "text-amber-400 font-medium"}>
              {scoredAt("square_duct") ? `Scored at Milestone ${scoredAt("square_duct")}` : "Greyed until Milestone 1"}</span>
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-white/10 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-neutral-200">nasa_wall_mounted_hump</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-neutral-800 text-neutral-400 font-mono">
              Re_c = 9.36e5
            </span>
          </div>
          <p className="text-xs text-neutral-400">
            NASA CFDVAL2004 benchmark case with severe adverse pressure gradient, flow separation, and reattachment.
          </p>
          <div className="pt-2 flex items-center gap-2 text-[11px] text-neutral-500">
            <span>Status:</span>
            <span className="text-amber-400 font-medium">Greyed until Milestone 2</span>
          </div>
        </div>
      </div>

      {/* Audit Log Card */}
      <div className="glass-panel p-4 rounded-xl border border-white/10 space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-300">
          Vault Access Audit Log (<code className="text-neutral-400">runs/vault_access.log</code>)
        </h3>
        <div className="p-3 rounded-lg bg-black/40 border border-white/5 font-mono text-xs text-neutral-400 space-y-1">
          <div className="text-emerald-400">
            [INIT] 2026-10-26T00:00:00Z - Split guard initialized: data/locked/ access restricted.
          </div>
          {evals.length === 0 && <div className="text-neutral-500">[LOG] No milestone evaluations executed yet. Budget remaining: 3 / 3 allowed evaluations.</div>}
          {evals.map((e, i) => (
            <div key={i} className="text-neutral-300">[MILESTONE {e.milestone}] {e.timestamp} · {e.mode} · {e.reason}</div>
          ))}
          {evals.length > 0 && <div className="text-amber-300">[LOG] Budget used: {q.data!.used} / {q.data!.max} locked evaluations on this machine.</div>}
        </div>
      </div>

      {evals.map((e, i) => (
        <div key={i} className="glass-panel p-4 rounded-xl border border-emerald-500/20 space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-300">
            Milestone {e.milestone} · frozen a-priori error ratio (candidate ÷ SST; below 1 beats SST)
          </h3>
          <table className="w-full text-xs">
            <thead><tr className="text-neutral-400 text-left">
              <th className="py-1">candidate</th>
              {Object.keys(rows(e)[0]?.cases ?? {}).map((c) => <th key={c} className="py-1">{c}</th>)}
              <th className="py-1">expression</th></tr></thead>
            <tbody>
              {[...rows(e)].sort((a, b) => (Object.values(a.cases)[0] ?? 9) - (Object.values(b.cases)[0] ?? 9)).map((r) => (
                <tr key={r.name} className="border-t border-white/5">
                  <td className="py-1 font-mono text-cyan-300">{r.name}</td>
                  {Object.values(r.cases).map((v, j) => <td key={j} className="py-1 font-mono text-emerald-300">{typeof v === "number" ? v.toFixed(3) : "—"}</td>)}
                  <td className="py-1 font-mono text-neutral-400 text-[10px]">{r.expr}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
