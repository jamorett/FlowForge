import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSessionState, startRound } from "../api/client";
import { AgentGraph } from "../components/AgentGraph";
import { CandidateFunnel, ProgressChart } from "../components/CandidateFunnel";
import { EventFeed } from "../components/EventFeed";
import { ChampionCard, RedTeamArena, SamPanel } from "../components/LabPanels";
import { useEvents, useLab } from "../state/events";

function Metric({ label, value, sub, accent = "text-white" }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="glass-panel p-3 rounded-xl border border-white/10">
      <div className="text-[11px] text-neutral-400">{label}</div>
      <div className={`text-lg font-bold font-mono ${accent}`}>{value}</div>
      {sub && <div className="text-[10px] text-neutral-500">{sub}</div>}
    </div>
  );
}

export function MissionControl({ session = "default" }: { session?: string }) {
  const st = useQuery({ queryKey: ["session", session], queryFn: () => fetchSessionState(session), refetchInterval: 5000 });
  const { connected, lastEventAt } = useEvents();
  const lab = useLab();
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const [live, setLive] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const noRedTeam = session.includes("no_redteam");

  async function onStart() { // starts a round in the session being watched (no second session box)
    setStarting(true); setNotice(null);
    try {
      const res = await startRound(session, !live);
      setNotice(res.status === "started" ? `Round started in “${res.session}” (${res.mock ? "mock, no spend" : "LIVE, spends API credits"}).`
        : res.status === "already_running" ? `“${res.session}” already has a running round.` : `Start rejected: ${res.reason ?? res.status}.`);
    } catch (e) {
      setNotice(`API offline — start the FastAPI server first. (${e instanceof Error ? e.message : e})`);
    } finally { setStarting(false); }
  }

  const idle = lastEventAt ? Math.round((now - lastEventAt) / 1000) : null;
  const survivors = lab.candidates.filter((c) => c.stage >= 5).length;
  const rejected = lab.candidates.filter((c) => c.status === "rejected").length;
  const best = lab.best?.worst_validation_ratio;

  return (
    <section aria-label="Mission control" className="space-y-4">
      <div className="glass-panel p-3 rounded-xl border border-white/10 flex flex-wrap items-center gap-3 text-xs">
        <span className="text-neutral-400">Watching <span className="font-mono text-cyan-300">{session}</span></span>
        <label className="flex items-center gap-2 text-neutral-300 cursor-pointer">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} className="accent-cyan-500" />
          Live (real API, spends credits)
        </label>
        <button onClick={onStart} disabled={starting}
          className="px-3 py-1.5 rounded-lg font-semibold bg-gradient-to-r from-cyan-600 to-blue-600 text-white border border-cyan-400/40 disabled:opacity-50">
          {starting ? "Starting…" : live ? "Start live round" : "Start mock round"}
        </button>
        {notice && <span className="text-neutral-400">{notice}</span>}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Metric label="Stream" value={connected ? "LIVE" : "offline"} accent={connected ? "text-emerald-300" : "text-neutral-500"}
          sub={idle === null ? "no events yet" : `last event ${idle}s ago`} />
        <Metric label="Rounds" value={String(lab.rounds.length)} sub={lab.roundNow !== undefined ? `now: round ${lab.roundNow}` : undefined} />
        <Metric label="Proposals" value={String(lab.candidates.length)} sub={`${rejected} rejected · ${survivors} passed R3`} />
        <Metric label="Champions" value={String(lab.champions.length)} sub={`${lab.breaks.length} red-team breaks`} />
        <Metric label="Best ratio vs SST" value={best !== undefined ? best.toFixed(3) : "—"} accent={best !== undefined && best < 1 ? "text-yellow-300" : "text-white"} sub="frozen · lower is better" />
        <Metric label="API spend (upper bound)" value={st.data ? `$${st.data.dollars_upper.toFixed(2)}` : "—"} sub={st.data ? `${st.data.tokens.toLocaleString()} tokens` : "API offline"} />
      </div>

      <AgentGraph lab={lab} />
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="glass-panel rounded-xl border border-white/10 p-2"><CandidateFunnel lab={lab} /></div>
        <div className="glass-panel rounded-xl border border-white/10 p-2"><ProgressChart lab={lab} /></div>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <ChampionCard champ={lab.best} />
        <RedTeamArena lab={lab} redteamEnabled={!noRedTeam} />
      </div>
      <SamPanel lab={lab} session={session} />
      <EventFeed />
    </section>
  );
}
