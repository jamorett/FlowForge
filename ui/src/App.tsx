import { useState } from "react";
import { CandidateInspector } from "./pages/CandidateInspector";
import { GeneralizationMatrix } from "./pages/GeneralizationMatrix";
import { MissionControl } from "./pages/MissionControl";
import { Replay } from "./pages/Replay";
import { Vault } from "./pages/Vault";

const VIEWS = [
  { id: "Mission Control", icon: "⚡", label: "Mission Control" },
  { id: "Generalization Matrix", icon: "▦", label: "Generalization Matrix" },
  { id: "Candidate Inspector", icon: "∫", label: "Candidate Inspector" },
  { id: "Vault", icon: "🔒", label: "Locked Vault" },
  { id: "Replay", icon: "↺", label: "Replay & Scrubber" },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

export function App() {
  const [view, setView] = useState<ViewId>("Mission Control");
  const [session, setSession] = useState("round-1");

  return (
    <div className="min-h-screen text-neutral-100 flex flex-col">
      {/* Top Navbar */}
      <header className="glass-panel border-b border-white/10 sticky top-0 z-50 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white shadow-[0_0_15px_rgba(6,182,212,0.4)]">
              FF
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base tracking-wide bg-gradient-to-r from-white via-neutral-200 to-neutral-400 bg-clip-text text-transparent">
                  FlowForge v2
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-cyan-950/70 text-cyan-300 border border-cyan-700/50">
                  Model Lab Cockpit
                </span>
              </div>
              <p className="text-[11px] text-neutral-400">
                Autonomous Turbulence Closure Discovery against OpenFOAM
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 glass-panel-subtle px-3 py-1.5 rounded-lg border border-white/5 text-xs">
              <span className="text-neutral-400">Session:</span>
              <input
                type="text"
                value={session}
                onChange={(e) => setSession(e.target.value)}
                className="bg-transparent text-cyan-300 font-mono text-xs focus:outline-none w-24 border-b border-cyan-500/30"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs text-neutral-400 font-mono">Paced ~20/s</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <div className="max-w-7xl mx-auto px-6 py-6 w-full flex-1 space-y-6">
        {/* Navigation Tabs */}
        <nav className="flex flex-wrap gap-2 p-1.5 glass-panel rounded-xl border border-white/10" aria-label="Views">
          {VIEWS.map((v) => {
            const active = view === v.id;
            return (
              <button
                key={v.id}
                onClick={() => setView(v.id)}
                className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-all ${
                  active
                    ? "bg-gradient-to-r from-cyan-600 to-blue-600 text-white shadow-[0_0_16px_rgba(6,182,212,0.3)] border border-cyan-400/40"
                    : "text-neutral-400 hover:text-neutral-200 hover:bg-white/5"
                }`}
              >
                <span>{v.icon}</span>
                <span>{v.label}</span>
              </button>
            );
          })}
        </nav>

        {/* View Pages */}
        <main className="transition-all duration-200">
          {view === "Mission Control" && <MissionControl />}
          {view === "Generalization Matrix" && <GeneralizationMatrix />}
          {view === "Candidate Inspector" && <CandidateInspector />}
          {view === "Vault" && <Vault />}
          {view === "Replay" && <Replay session={session} />}
        </main>
      </div>

      {/* Footer */}
      <footer className="border-t border-white/5 py-4 text-center text-xs text-neutral-500 font-mono">
        FlowForge v2 · Strict Physics Guardrails & Deterministic Verification · RP1–RP6 Benchmark
      </footer>
    </div>
  );
}
