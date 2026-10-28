import { useState } from "react";
import { EquationView } from "../components/EquationView";

const SAMPLE_CANDIDATES = [
  {
    id: "cand_sparta_curv",
    formula: "a^{\\Delta}_{ij} = -0.05\\,I_1\\,T^{(1)}_{ij} + 0.02\\,T^{(2)}_{ij}",
    complexity: 8,
    dl: 42.5,
    snapped: true,
    mechanisms: ["streamline_curvature", "anisotropy_production"],
    worst_case_error: 0.82,
    pope_bases: ["T1", "T2"],
    invariants: ["I1"],
  },
  {
    id: "cand_tanh_damped",
    formula: "a^{\\Delta}_{ij} = -0.08\\,\\tanh(I_1)\\,T^{(1)}_{ij}",
    complexity: 5,
    dl: 31.2,
    snapped: true,
    mechanisms: ["streamline_curvature"],
    worst_case_error: 0.88,
    pope_bases: ["T1"],
    invariants: ["I1"],
  },
  {
    id: "cand_gated_composite",
    formula: "a^{\\Delta}_{ij} = \\sigma(w I + b)\\,a^{(M_1)}_{ij} + (1 - \\sigma(w I + b))\\,a^{(M_2)}_{ij}",
    complexity: 16,
    dl: 68.4,
    snapped: false,
    mechanisms: ["composite_gated", "separation_bubble_delay"],
    worst_case_error: 0.74,
    pope_bases: ["T1", "T2", "T3"],
    invariants: ["I1", "I2"],
  },
];

export function CandidateInspector() {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const cand = SAMPLE_CANDIDATES[selectedIdx];

  return (
    <section aria-label="Candidate inspector" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Candidate Closure Inspector</h2>
          <p className="text-xs text-neutral-400 mt-1">
            Mathematical formula inspection, Pope tensor bases, complexity analysis, and description length breakdown.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {SAMPLE_CANDIDATES.map((c, i) => (
            <button
              key={c.id}
              onClick={() => setSelectedIdx(i)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium border transition-all ${
                selectedIdx === i
                  ? "bg-cyan-950/70 border-cyan-500 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.2)]"
                  : "bg-neutral-900/40 border-white/10 text-neutral-400 hover:text-neutral-200"
              }`}
            >
              {c.id}
            </button>
          ))}
        </div>
      </div>

      {/* Main Formula Card */}
      <div className="space-y-3">
        <EquationView tex={cand.formula} label={`Anisotropy Correction Tensor · ${cand.id}`} />
      </div>

      {/* Properties Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="glass-panel p-4 rounded-xl border border-white/10">
          <div className="text-xs text-neutral-400 font-medium">AST Node Complexity</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">{cand.complexity}</span>
            <span className="text-xs text-neutral-500">/ 25 max cap</span>
          </div>
          <div className="w-full bg-neutral-800 h-1.5 rounded-full mt-3 overflow-hidden">
            <div
              className={`h-full ${
                cand.complexity <= 25 ? "bg-emerald-400" : "bg-rose-400"
              }`}
              style={{ width: `${(cand.complexity / 25) * 100}%` }}
            />
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-white/10">
          <div className="text-xs text-neutral-400 font-medium">Description Length (MDL)</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-cyan-300">{cand.dl}</span>
            <span className="text-xs text-neutral-500">bits</span>
          </div>
          <div className="text-[11px] text-neutral-500 mt-2">
            Includes tree vocab, constants & gate penalty
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-white/10">
          <div className="text-xs text-neutral-400 font-medium">Constant Snapping</div>
          <div className="mt-1">
            <span
              className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                cand.snapped
                  ? "bg-emerald-950/70 border border-emerald-500/40 text-emerald-300"
                  : "bg-amber-950/70 border border-amber-500/40 text-amber-300"
              }`}
            >
              {cand.snapped ? "Snapped (<= 1% delta)" : "Raw Continuous Fit"}
            </span>
          </div>
          <div className="text-[11px] text-neutral-500 mt-2">
            Rationals: {"{0, ±1, ±0.5, ±0.05, ±1.5}"}
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-white/10">
          <div className="text-xs text-neutral-400 font-medium">Worst-Case Error vs SST</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-emerald-400">
              {cand.worst_case_error.toFixed(2)}x
            </span>
            <span className="text-xs text-neutral-500">minimax</span>
          </div>
          <div className="text-[11px] text-neutral-500 mt-2">
            {(100 * (1.0 - cand.worst_case_error)).toFixed(0)}% error reduction vs baseline
          </div>
        </div>
      </div>

      {/* Physics Decomposition Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-panel p-4 rounded-xl border border-white/10 space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
            Active Pope Tensor Basis & Invariants
          </h4>
          <div className="flex flex-wrap gap-2 pt-1">
            {cand.pope_bases.map((t) => (
              <span
                key={t}
                className="px-2.5 py-1 rounded-md text-xs font-mono font-semibold bg-purple-950/50 text-purple-300 border border-purple-700/40"
              >
                Basis {t} (Symmetric & Traceless)
              </span>
            ))}
            {cand.invariants.map((inv) => (
              <span
                key={inv}
                className="px-2.5 py-1 rounded-md text-xs font-mono font-semibold bg-blue-950/50 text-blue-300 border border-blue-700/40"
              >
                Invariant {inv}
              </span>
            ))}
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-white/10 space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
            Attributed Physical Mechanisms
          </h4>
          <div className="flex flex-wrap gap-2 pt-1">
            {cand.mechanisms.map((m) => (
              <span
                key={m}
                className="px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-950/50 text-emerald-300 border border-emerald-700/40"
              >
                {m.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
