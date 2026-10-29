import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EquationView } from "../components/EquationView";
import { fetchLatestRegions, fetchMatrix } from "../api/client";

// Offline samples: shown ONLY when the backend has no live candidates.
// Labeled as such; never presented as session results.
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

export function CandidateInspector({ session = "default" }: { session?: string }) {
  const matrix = useQuery({ queryKey: ["matrix", session], queryFn: () => fetchMatrix(session) });
  const regions = useQuery({ queryKey: ["regions", session], queryFn: () => fetchLatestRegions(session) });
  const [selectedIdx, setSelectedIdx] = useState(0);

  const live = (matrix.data?.candidates ?? []).filter(Boolean);
  const isLive = live.length > 0;
  const cand = SAMPLE_CANDIDATES[selectedIdx % SAMPLE_CANDIDATES.length];
  const liveId = isLive ? live[selectedIdx % live.length] : null;
  const liveCells = (matrix.data?.cells ?? []).filter((c) => c.candidate === liveId);
  const liveErrors = liveCells.map((c) => c.error).filter((e): e is number => typeof e === "number");
  const liveWorst = liveErrors.length ? Math.max(...liveErrors) : null;

  return (
    <section aria-label="Candidate inspector" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Candidate Closure Inspector</h2>
          <p className="text-xs text-neutral-400 mt-1">
            {isLive
              ? `Live session “${session}”: ${live.length} candidate(s) from the event stream.`
              : "Backend has no candidates yet — showing offline samples. Start a session to go live."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
              isLive
                ? "bg-emerald-950/70 border-emerald-500/40 text-emerald-300"
                : "bg-amber-950/70 border-amber-500/40 text-amber-300"
            }`}
          >
            {isLive ? "LIVE" : "OFFLINE SAMPLES"}
          </span>
        </div>
      </div>

      {matrix.isError && (
        <p className="text-sm text-amber-300">API offline — start the FastAPI server to load live candidates.</p>
      )}

      {/* Candidate selector */}
      <div className="flex items-center gap-2 flex-wrap">
        {(isLive ? live : SAMPLE_CANDIDATES.map((c) => c.id)).map((id, i) => (
          <button
            key={id}
            onClick={() => setSelectedIdx(i)}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium border transition-all ${
              selectedIdx % (isLive ? live.length : SAMPLE_CANDIDATES.length) === i
                ? "bg-cyan-950/70 border-cyan-500 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.2)]"
                : "bg-neutral-900/40 border-white/10 text-neutral-400 hover:text-neutral-200"
            }`}
          >
            {id}
          </button>
        ))}
      </div>

      {/* Main Formula Card */}
      <div className="space-y-3">
        <EquationView tex={liveId ?? cand.formula} label={`Anisotropy Correction Tensor · ${liveId ?? cand.id}`} />
        {isLive && (
          <div className="glass-panel p-4 rounded-xl border border-white/10 text-xs text-neutral-300">
            <span className="font-mono text-cyan-300">{liveId}</span>
            {liveWorst !== null ? (
              <span> — worst recorded error <span className="font-bold text-white">{liveWorst.toFixed(3)}</span> across {liveCells.length} scored cell(s).</span>
            ) : (
              <span> — no scored cells yet in this session.</span>
            )}
          </div>
        )}
      </div>

      {/* SAM / error-region panel */}
      <div className="glass-panel p-4 rounded-xl border border-white/10 space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 flex items-center justify-between">
          <span>Error regions (SAM segmentation)</span>
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
              regions.data?.source === "sam-3.1"
                ? "bg-cyan-950/60 text-cyan-300 border-cyan-700/50"
                : "bg-neutral-800 text-neutral-400 border-white/10"
            }`}
          >
            {regions.data ? `source: ${regions.data.source}` : regions.isLoading ? "loading…" : "unavailable"}
          </span>
        </h4>
        {regions.data && regions.data.regions.length > 0 ? (
          <ul className="text-xs text-neutral-300 space-y-1 font-mono">
            {regions.data.regions.map((r, i) => (
              <li key={i}>
                {r.region} box [{r.box.join(", ")}]
                {typeof r.mean_error === "number" ? ` mean ${r.mean_error.toFixed(4)}` : ""}
                {typeof r.max_error === "number" ? ` max ${r.max_error.toFixed(4)}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[11px] text-neutral-500">
            {regions.data?.detail ?? "No rendered error map in this session yet."}
          </p>
        )}
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
              {(liveWorst ?? cand.worst_case_error).toFixed(2)}x
            </span>
            <span className="text-xs text-neutral-500">minimax</span>
          </div>
          <div className="text-[11px] text-neutral-500 mt-2">
            {(100 * (1.0 - (liveWorst ?? cand.worst_case_error))).toFixed(0)}% error reduction vs baseline
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
