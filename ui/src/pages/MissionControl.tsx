import { useQuery } from "@tanstack/react-query";
import { fetchSessionState } from "../api/client";
import { EventFeed } from "../components/EventFeed";
import { StatusBadge } from "../components/StatusBadge";

const ROLES = [
  { name: "Board", model: "muse-spark-1.3", role: "Directs round planning, group staffing & budgets", status: "active" },
  { name: "Theorist", model: "muse-spark-1.3", role: "Proposes closure tensor expressions (complexity <= 25)", status: "active" },
  { name: "Coder", model: "muse-code", role: "Fits constants via elastic net & snaps within 1%", status: "active" },
  { name: "Analyst", model: "muse-spark-1.3", role: "Diagnoses regional error maps & recirculation zones", status: "idle" },
  { name: "Skeptic", model: "muse-spark-1.3", role: "Attacks correctness & elegance from separate context", status: "idle" },
  { name: "Red Team", model: "muse-spark-1.3", role: "Deforms flow geometries to break champions", status: "active" },
  { name: "Composer", model: "muse-spark-1.3", role: "Composes surviving modules with sigmoid gates (+16 bits)", status: "idle" },
];

export function MissionControl() {
  const q = useQuery({ queryKey: ["session"], queryFn: () => fetchSessionState() });

  return (
    <section aria-label="Mission control" className="space-y-6">
      {/* Header Metrics Banner */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="glass-panel p-4 rounded-xl border border-white/10">
          <div className="text-xs text-neutral-400 font-medium">Session Status</div>
          <div className="mt-1 flex items-center justify-between">
            <span className="text-lg font-bold text-white">
              {q.data?.exists ? "Active Stream" : "Standby"}
            </span>
            <StatusBadge
              ok={!!q.data?.exists}
              label={q.data?.exists ? "Connected" : "No stream"}
            />
          </div>
          <div className="text-[11px] text-neutral-500 mt-2 font-mono">
            {q.data ? `${q.data.event_count} events · ${q.data.events_per_second}/s` : "Waiting for backend"}
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-white/10">
          <div className="text-xs text-neutral-400 font-medium">Token Budget Meter</div>
          <div className="mt-1 flex items-center justify-between">
            <span className="text-lg font-bold text-cyan-300">$0.00 / $50.00</span>
            <span className="text-xs px-2 py-0.5 rounded bg-cyan-950/60 text-cyan-400 border border-cyan-800/40">
              Hard Cap
            </span>
          </div>
          <div className="w-full bg-neutral-800 h-1.5 rounded-full mt-3 overflow-hidden">
            <div className="bg-cyan-400 h-full w-[2%]" />
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-white/10">
          <div className="text-xs text-neutral-400 font-medium">Evaluation Ladder Rungs</div>
          <div className="mt-1 flex items-center gap-1.5">
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-blue-950/60 text-blue-300 border border-blue-800/40">R0: Limits</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-blue-950/60 text-blue-300 border border-blue-800/40">R1: A Priori</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-950/60 text-indigo-300 border border-indigo-800/40">R2: Short</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-950/60 text-purple-300 border border-purple-800/40">R3: Full</span>
          </div>
          <div className="text-[11px] text-neutral-500 mt-2">
            Top 50% advance at each halving rung
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-white/10">
          <div className="text-xs text-neutral-400 font-medium">Active Research Groups</div>
          <div className="mt-1 text-lg font-bold text-white">7 Swarm Roles</div>
          <div className="text-[11px] text-neutral-500 mt-2">
            Independent roles, structured schema outputs
          </div>
        </div>
      </div>

      {/* Main Grid: Swarm Roles + Event Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Swarm Roles Card */}
        <div className="lg:col-span-1 glass-panel p-5 rounded-xl border border-white/10 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-neutral-300 flex items-center justify-between">
            <span>Swarm Staffing</span>
            <span className="text-[11px] font-mono text-cyan-400">Meta Model API</span>
          </h3>

          <div className="space-y-2 text-xs">
            {ROLES.map((r) => (
              <div
                key={r.name}
                className="p-2.5 rounded-lg bg-neutral-900/50 border border-white/5 hover:border-white/15 transition-all"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-neutral-200">{r.name}</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-neutral-800 text-neutral-400">
                    {r.model}
                  </span>
                </div>
                <p className="text-[11px] text-neutral-400 mt-1 leading-snug">
                  {r.role}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Live Stream Event Feed */}
        <div className="lg:col-span-2">
          <EventFeed />
        </div>
      </div>
    </section>
  );
}
