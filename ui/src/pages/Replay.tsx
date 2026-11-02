import { useEffect, useState } from "react";
import { AgentGraph } from "../components/AgentGraph";
import { CandidateFunnel, ProgressChart } from "../components/CandidateFunnel";
import { EventFeed } from "../components/EventFeed";
import { ChampionCard } from "../components/LabPanels";
import { useEvents, useLab } from "../state/events";

const SPEEDS = { "1×": 1000, "4×": 250, "16×": 62 } as const;

/** Zero-token playback of a recorded session: every view re-derived at the cursor. */
export function Replay({ session = "round-1" }: { session?: string }) {
  const { events } = useEvents();
  const total = events.length;
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<keyof typeof SPEEDS>("4×");
  const lab = useLab(cursor);

  useEffect(() => { setCursor(0); setPlaying(false); }, [session]);
  useEffect(() => {
    if (!playing) return;
    if (cursor >= total) { setPlaying(false); return; }
    const t = setTimeout(() => setCursor((c) => Math.min(total, c + 1)), SPEEDS[speed]);
    return () => clearTimeout(t);
  }, [playing, cursor, total, speed]);

  const btn = "px-3 py-1.5 rounded-lg text-xs font-semibold border border-white/10";
  return (
    <section aria-label="Replay" className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white">Session replay · <span className="font-mono text-cyan-300">{session}</span></h2>
        <p className="text-xs text-neutral-400">Re-plays the recorded <code>events.jsonl</code>: no model calls, no tokens. Every panel is derived at the cursor.</p>
      </div>
      <div className="glass-panel p-3 rounded-xl border border-white/10 flex flex-wrap items-center gap-3">
        <button className={`${btn} bg-emerald-600 text-white`} onClick={() => { if (cursor >= total) setCursor(0); setPlaying(true); }} disabled={!total}>▶ Play</button>
        <button className={`${btn} bg-white/5 text-neutral-300`} onClick={() => setPlaying(false)}>⏸ Pause</button>
        <button className={`${btn} bg-white/5 text-neutral-300`} onClick={() => { setPlaying(false); setCursor((c) => Math.min(total, c + 1)); }}>⏭ Step</button>
        <button className={`${btn} bg-white/5 text-neutral-300`} onClick={() => { setPlaying(false); setCursor(0); }}>⏮ Restart</button>
        <select value={speed} onChange={(e) => setSpeed(e.target.value as keyof typeof SPEEDS)} className="bg-neutral-900 text-cyan-300 text-xs rounded px-2 py-1 border border-white/10">
          {Object.keys(SPEEDS).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input type="range" min={0} max={total} value={cursor} onChange={(e) => { setPlaying(false); setCursor(Number(e.target.value)); }} className="flex-1 min-w-[200px] accent-cyan-500" aria-label="Replay position" />
        <span className="font-mono text-xs text-neutral-400">{cursor} / {total} events</span>
      </div>
      <AgentGraph lab={lab} live={false} />
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="glass-panel rounded-xl border border-white/10 p-2"><CandidateFunnel lab={lab} /></div>
        <div className="glass-panel rounded-xl border border-white/10 p-2"><ProgressChart lab={lab} /></div>
      </div>
      <ChampionCard champ={lab.best} title="Best champion at this point" />
      <EventFeed upto={cursor} />
    </section>
  );
}
