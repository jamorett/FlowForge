import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSessionState } from "../api/client";
import { AgentGraph } from "../components/AgentGraph";
import { CandidateFunnel, ClusterView, ProgressChart } from "../components/CandidateFunnel";
import { EventFeed } from "../components/EventFeed";
import { ChampionCard, RedTeamArena, SamPanel } from "../components/LabPanels";
import { RunPanel } from "../components/RunPanel";
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

export function MissionControl({ session = "default", onWatch = () => {} }: { session?: string; onWatch?: (s: string) => void }) {
  const st = useQuery({ queryKey: ["session", session], queryFn: () => fetchSessionState(session), refetchInterval: 5000 });
  const { connected, lastEventAt } = useEvents();
  const lab = useLab();
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const noRedTeam = session.includes("no_redteam");

  const idle = lastEventAt ? Math.round((now - lastEventAt) / 1000) : null;
  const survivors = lab.candidates.filter((c) => c.stage >= 5).length;
  const rejected = lab.candidates.filter((c) => c.status === "rejected").length;
  const best = lab.best?.worst_validation_ratio;

  return (
    <section aria-label="Mission control" className="space-y-4">
      <RunPanel session={session} onWatch={onWatch} />

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
        <div className="glass-panel rounded-xl border border-white/10 p-2"><ClusterView lab={lab} /></div>
        <ChampionCard champ={lab.best} />
      </div>
      <RedTeamArena lab={lab} redteamEnabled={!noRedTeam} />
      <SamPanel lab={lab} session={session} />
      <EventFeed />
    </section>
  );
}
