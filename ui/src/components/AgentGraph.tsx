import { useEffect, useState } from "react";
import { flowOf, prefersReducedMotion, type Lab, type Role } from "../state/events";

// Round order as a closed circuit: top row, the ladder down the right, review row back, loop to Board.
const POS_V1: Partial<Record<Role, [number, number]>> = {
  board: [70, 70], theorist: [220, 70], coder: [370, 70], fit: [520, 70], rung0: [670, 70], rung1: [820, 70],
  rung2: [940, 190], rung3: [820, 310], analyst: [670, 310], skeptic: [520, 310], redteam: [370, 310],
  composer: [220, 310], champion: [70, 310],
};
// Loop v2 circuit: diagnose -> propose -> score -> revise -> re-score -> population -> champion -> next round.
const POS_V2: Partial<Record<Role, [number, number]>> = {
  diagnostician: [110, 110], theorist: [330, 70], score: [580, 70], revise: [870, 110],
  score_revised: [870, 280], population: [580, 310], champion: [330, 310],
};
const LABEL: Partial<Record<Role, string>> = {
  diagnostician: "Diagnostician", score: "Fit + score", revise: "Reviser", score_revised: "Re-score", population: "Population",
  board: "Board", theorist: "Theorists", coder: "Coder", fit: "Fitter", rung0: "R0 limits", rung1: "R1 a priori",
  rung2: "R2 short", rung3: "R3 realizable", analyst: "Analyst + SAM", skeptic: "Skeptic", redteam: "Red Team",
  composer: "Composer", champion: "Champion",
};
const COLOR: Partial<Record<Role, string>> = {
  board: "#a78bfa", theorist: "#22d3ee", coder: "#34d399", fit: "#34d399", analyst: "#38bdf8",
  skeptic: "#fbbf24", redteam: "#fb7185", composer: "#e879f9", champion: "#facc15",
  diagnostician: "#a78bfa", revise: "#22d3ee", score: "#34d399", score_revised: "#34d399", population: "#38bdf8",
};
const color = (r: Role) => COLOR[r] ?? "#60a5fa";

function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return now;
}

/** What each node did in the current round, from the derived lab model only. */
function badges(lab: Lab, round?: number): Partial<Record<Role, string>> {
  if (round === undefined) return {};
  if (lab.loop === "v2") return badgesV2(lab, round);
  const c = lab.candidates.filter((x) => x.round === round);
  const atLeast = (s: number) => c.filter((x) => x.stage >= s).length;
  const champ = lab.champions.find((x) => x.round === round);
  const att = lab.attacks.filter((a) => a.round === round).length;
  const brk = lab.breaks.filter((b) => b.round === round).length;
  const an = lab.analyst.find((a) => a.round === round);
  return {
    theorist: `${c.length} proposed`, fit: `${atLeast(1)} fitted`, rung0: `${atLeast(2)} pass`, rung1: `${atLeast(3)} pass`,
    rung2: `${atLeast(4)} pass`, rung3: `${atLeast(5)} pass`,
    analyst: an ? `${an.regions.length} regions` : "", skeptic: `${lab.objections.filter((o) => o.round === round).length} objections`,
    redteam: att || brk ? `${att} attacks · ${brk} breaks` : "", champion: champ?.worst_validation_ratio !== undefined
      ? `ratio ${champ.worst_validation_ratio.toFixed(3)}` : c.length ? "none yet" : "",
  };
}

function badgesV2(lab: Lab, round: number): Partial<Record<Role, string>> {
  const evs = lab.events.filter((e) => e.round === round);
  const count = (step: string, key: string) => evs.filter((e) => e.step === step).reduce((n, e) => n + (e[key]?.length ?? 0), 0);
  const scored = (step: string) => evs.filter((e) => e.step === step).flatMap((e) => e.candidates ?? []);
  const usable = (xs: any[]) => xs.filter((c) => c.status === "ok" && c.realizable).length;
  const champ = lab.champions.find((x) => x.round === round);
  const pop = lab.population.find((p) => p.round === round);
  const diag = lab.analyst.find((a) => a.round === round);
  return {
    diagnostician: diag ? (diag.failure_regions[0] ?? "diagnosed") : "",
    theorist: `${count("theorist", "expressions")} proposed`, score: `${usable(scored("score"))} usable`,
    revise: `${count("revise", "expressions")} revised`, score_revised: `${usable(scored("score_revised"))} usable`,
    population: pop ? `${pop.size} kept` : "",
    champion: champ?.worst_validation_ratio !== undefined ? `ratio ${champ.worst_validation_ratio.toFixed(3)}` : "",
  };
}

export function AgentGraph({ lab, live = true }: { lab: Lab; live?: boolean }) {
  const FLOW = flowOf(lab.loop);
  const POS = (lab.loop === "v2" ? POS_V2 : POS_V1) as Record<Role, [number, number]>;
  const now = useNow();
  const motion = !prefersReducedMotion();
  const last = lab.lastRole;
  const prev = (() => { // role before the latest step, for the travelling dot
    const steps = lab.events.filter((e) => e.step && (FLOW as readonly string[]).includes(e.step));
    return steps.length > 1 ? (steps[steps.length - 2].step as Role) : undefined;
  })();
  const next = last ? FLOW[(FLOW.indexOf(last) + 1) % FLOW.length] : undefined;
  const idleS = lab.lastAt ? Math.max(0, Math.round((now - lab.lastAt) / 1000)) : null;
  const b = badges(lab, lab.roundNow);
  const edges = FLOW.map((r, i) => [r, FLOW[(i + 1) % FLOW.length]] as [Role, Role]);

  return (
    <div className="glass-panel rounded-xl border border-white/10 p-3">
      <div className="flex items-center justify-between px-2 pb-1 text-xs">
        <span className="font-semibold uppercase tracking-wider text-neutral-300">Agent interaction graph</span>
        <span className="font-mono text-neutral-400">
          {lab.roundNow !== undefined ? `round ${lab.roundNow}` : "waiting for events"}
          {live && next && idleS !== null ? ` · ${LABEL[next] ?? next} working… ${idleS}s` : ""}
          {lab.loop === "v2" ? " · loop v2" : ""}
        </span>
      </div>
      <svg viewBox="0 0 1010 380" className="w-full h-auto" role="img" aria-label="Agents and the evaluation ladder; the active agent pulses">
        <defs>
          <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="#475569" />
          </marker>
          <filter id="glow"><feGaussianBlur stdDeviation="4" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        {edges.map(([a, z]) => {
          const [x1, y1] = POS[a], [x2, y2] = POS[z];
          const active = a === prev && z === last;
          return <line key={a + z} x1={x1} y1={y1} x2={x2} y2={y2} stroke={active ? color(z) : "#334155"}
            strokeWidth={active ? 3 : 1.5} strokeDasharray={a === "champion" ? "6 6" : undefined} markerEnd="url(#arr)" opacity={0.9} />;
        })}
        {FLOW.map((r) => {
          const [x, y] = POS[r];
          const isLast = r === last, isNext = live && r === next;
          return (
            <g key={r}>
              {isLast && motion && (
                <circle cx={x} cy={y} r={34} fill="none" stroke={color(r)} strokeWidth={2}>
                  <animate attributeName="r" from="34" to="56" dur="1.4s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.9" to="0" dur="1.4s" repeatCount="indefinite" />
                </circle>
              )}
              {isNext && (
                <circle cx={x} cy={y} r={40} fill="none" stroke={color(r)} strokeWidth={2} strokeDasharray="8 10" opacity={0.8}>
                  {motion && <animateTransform attributeName="transform" type="rotate" from={`0 ${x} ${y}`} to={`360 ${x} ${y}`} dur="3s" repeatCount="indefinite" />}
                </circle>
              )}
              <circle cx={x} cy={y} r={32} fill={isLast ? color(r) : "#0f172a"} fillOpacity={isLast ? 0.25 : 1}
                stroke={color(r)} strokeWidth={isLast ? 3 : 1.5} filter={isLast ? "url(#glow)" : undefined} />
              <text x={x} y={y + 4} textAnchor="middle" fontSize="11" fontWeight="600" fill="#e2e8f0">{LABEL[r] ?? r}</text>
              {b[r] && <text x={x} y={y + 50} textAnchor="middle" fontSize="11" fill={color(r)} fontFamily="monospace">{b[r]}</text>}
            </g>
          );
        })}
        {motion && prev && last && (
          // remounted per event: a pulse of "work" travelling to the agent that just acted
          <circle key={lab.events.length} r={7} fill={color(last)} filter="url(#glow)">
            <animateMotion dur="0.8s" fill="freeze" path={`M ${POS[prev][0]} ${POS[prev][1]} L ${POS[last][0]} ${POS[last][1]}`} />
          </circle>
        )}
        <text x={505} y={182} textAnchor="middle" fontSize="13" fill="#94a3b8">
          {lab.best ? "best champion so far" : "no champion yet"}
        </text>
        <text x={505} y={210} textAnchor="middle" fontSize="22" fontWeight="700" fill="#facc15">
          {lab.best?.worst_validation_ratio !== undefined ? `${lab.best.worst_validation_ratio.toFixed(3)} × SST error` : "—"}
        </text>
        <text x={505} y={234} textAnchor="middle" fontSize="11" fill="#64748b">
          worst-case validation ratio · a priori (frozen) · lower is better
        </text>
      </svg>
    </div>
  );
}
