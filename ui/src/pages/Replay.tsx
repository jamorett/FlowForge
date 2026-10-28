import { useState } from "react";
import { EventFeed } from "../components/EventFeed";

export function Replay({ session = "round-1" }: { session?: string }) {
  const [activeSession, setActiveSession] = useState(session);
  const [speed, setSpeed] = useState("20");

  return (
    <section aria-label="Replay and Scrubber" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <span>↺</span>
            <span>Deterministic Session Replay</span>
          </h2>
          <p className="text-xs text-neutral-400 mt-1">
            Zero-token reproducible playback: re-feeds recorded responses from <code className="text-neutral-300">events.jsonl</code>.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 glass-panel-subtle px-3 py-1.5 rounded-lg border border-white/5 text-xs">
            <span className="text-neutral-400">Pace:</span>
            <select
              value={speed}
              onChange={(e) => setSpeed(e.target.value)}
              className="bg-transparent text-cyan-300 font-mono text-xs focus:outline-none"
            >
              <option value="5" className="bg-neutral-900 text-neutral-200">5 events/s</option>
              <option value="20" className="bg-neutral-900 text-neutral-200">20 events/s (Default)</option>
              <option value="50" className="bg-neutral-900 text-neutral-200">50 events/s (Fast)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Scrubber Controls Banner */}
      <div className="glass-panel p-4 rounded-xl border border-white/10 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_12px_rgba(16,185,129,0.3)] transition-all">
            ▶ Play Replay
          </button>
          <button className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/5 hover:bg-white/10 text-neutral-300 border border-white/10 transition-all">
            ⏸ Pause
          </button>
          <button className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/5 hover:bg-white/10 text-neutral-300 border border-white/10 transition-all">
            ⏭ Step Next
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="text-neutral-400">Target Session:</span>
          <input
            type="text"
            value={activeSession}
            onChange={(e) => setActiveSession(e.target.value)}
            className="glass-panel-subtle px-2 py-1 rounded text-cyan-300 font-mono text-xs border border-white/10 w-28"
          />
        </div>
      </div>

      {/* Stream Viewer */}
      <EventFeed session={activeSession} />
    </section>
  );
}
