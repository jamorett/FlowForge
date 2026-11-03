import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { eventsSocket } from "../api/client";

export type Ev = Record<string, any> & { _i: number; _t: number };

// Ladder order of the round; every view (graph, funnel, replay) reads this one list.
export const FLOW = ["board", "theorist", "coder", "fit", "rung0", "rung1", "rung2", "rung3",
  "analyst", "skeptic", "redteam", "composer", "champion"] as const;
// Loop v2 (flowforge/orchestrator/loop_v2.py): diagnose -> propose -> score -> revise -> population -> champion.
export const FLOW_V2 = ["diagnostician", "theorist", "score", "revise", "score_revised", "population", "champion"] as const;
export type Role = (typeof FLOW)[number] | (typeof FLOW_V2)[number];
export type Loop = "v1" | "v2";
export const flowOf = (loop: Loop): readonly Role[] => (loop === "v2" ? FLOW_V2 : FLOW);
export const STAGES = ["proposed", "fitted", "R0 limits", "R1 a priori", "R2 short", "R3 realizable", "champion"];

export interface Cand {
  expr: string; original: string; round: number; group?: string; stage: number;
  status: "alive" | "rejected" | "champion"; reason?: string; mse?: number;
}
export interface Champion {
  round: number; expression: string; dl?: number; worst_validation_ratio?: number;
  train?: { ratio?: number }; validation?: Record<string, { ratio?: number }>; attack_ratios?: Record<string, number>;
}
export interface Lab {
  events: Ev[]; rounds: number[]; candidates: Cand[]; champions: Champion[]; best?: Champion;
  attacks: { round: number; case_id: string; failure?: string; alpha?: number }[];
  breaks: { round: number; expression?: string; case_id?: string; ratio?: number }[];
  analyst: { round: number; image?: string; regions: any[]; source?: string; failure_regions: string[]; next_hypothesis?: string }[];
  objections: { round: number; text: string }[];
  tokens: number; lastRole?: Role; lastAt?: number; roundNow?: number;
  loop: Loop; population: { round: number; size: number }[];
}

const names = (xs: unknown): string[] =>
  Array.isArray(xs) ? xs.map((s) => (typeof s === "string" ? s : s?.expression)).filter((s): s is string => !!s) : [];

/** Pure: raw events -> lab model. Rejections are inferred like history.py: present at rung k, absent at k+1. */
export function deriveLab(events: Ev[]): Lab {
  const loop: Loop = events.some((e) => e.loop === "v2") ? "v2" : "v1";
  const flow = flowOf(loop) as readonly string[];
  const lab: Lab = { events, rounds: [], candidates: [], champions: [], attacks: [], breaks: [], analyst: [], objections: [],
    tokens: 0, loop, population: [] };
  const byRound = new Map<number, Ev[]>();
  for (const e of events) {
    if (typeof e.tokens === "number" && !e.step) lab.tokens += e.tokens;
    if (typeof e.round !== "number") continue;
    if (!byRound.has(e.round)) byRound.set(e.round, []);
    byRound.get(e.round)!.push(e);
    if (e.step && flow.includes(e.step)) { lab.lastRole = e.step as Role; lab.lastAt = e._t; lab.roundNow = e.round; }
  }
  lab.rounds = [...byRound.keys()].sort((a, b) => a - b);
  for (const r of lab.rounds) {
    const evs = byRound.get(r)!;
    const step = (s: string) => evs.filter((e) => e.step === s);
    if (loop === "v2") { deriveRoundV2(lab, r, step); continue; }
    const fitOf = new Map<string, any>();
    for (const f of step("fit")) for (const x of f.fits ?? []) if (x?.original) fitOf.set(x.original, x);
    const pass = [0, 1, 2, 3].map((k) => step(`rung${k}`).length ? new Set(step(`rung${k}`).flatMap((e) => names(e.survivors))) : null);
    const nonReal = new Set(step("rung2").flatMap((e) => names(e.non_realizable)));
    const champ = step("champion").map((e) => e.champion).find((c) => c && c.expression);
    const done = (stage: number) => stage === 1 ? step("fit").length > 0 : stage >= 2 && stage <= 5 ? pass[stage - 2] !== null : false;
    for (const t of step("theorist")) {
      for (const original of names(t.expressions)) {
        const fit = fitOf.get(original);
        const expr: string = fit?.expression ?? original;
        let stage = 0;
        if (fit && (fit.status === "ok" || fit.status === "no_improvement")) stage = 1;
        for (let k = 0; k < 4 && stage === k + 1; k++) if (pass[k]?.has(expr)) stage = k + 2;
        const isChamp = !!champ && champ.expression === expr && stage === 5;
        let reason: string | undefined;
        if (!isChamp && stage === 5 && step("champion").length) {
          reason = "passed every rung; not selected (champion rule: within 3% of best, shortest DL)";
        } else if (!isChamp && done(stage + 1)) {
          reason = stage === 0 ? `fit ${fit?.status ?? "missing"}`
            : nonReal.has(expr) || stage === 4 ? "non-realizable (left the Lumley triangle)"
            : stage === 1 ? "failed rung 0 (limits / grammar)" : "halved: lower a priori accuracy";
        }
        lab.candidates.push({ expr, original, round: r, group: t.group, stage: isChamp ? 6 : stage,
          status: isChamp ? "champion" : reason ? "rejected" : "alive", reason, mse: fit?.mse_after ?? undefined });
      }
    }
    if (champ) lab.champions.push({ round: r, ...champ });
    for (const e of step("redteam")) {
      for (const a of e.attacks ?? []) lab.attacks.push({ round: r, case_id: a.case_id ?? a.flow?.case_id, failure: a.flow?.intended_failure_mode, alpha: a.flow?.alpha });
      for (const b of e.breaks ?? []) lab.breaks.push({ round: r, ...b });
    }
    for (const e of step("analyst")) {
      const reg = (e.regions ?? [])[0] ?? {};
      lab.analyst.push({ round: r, image: reg.image, regions: reg.regions ?? [], source: reg.regions?.[0]?.source ?? reg.source,
        failure_regions: (e.failure_regions ?? []).map(String), next_hypothesis: e.next_hypothesis });
    }
    for (const e of step("skeptic")) for (const o of e.objections ?? []) lab.objections.push({ round: r, text: String(o) });
  }
  const scored = lab.champions.filter((c) => typeof c.worst_validation_ratio === "number");
  lab.best = scored.sort((a, b) => a.worst_validation_ratio! - b.worst_validation_ratio!)[0];
  return lab;
}

/** Loop v2 round: candidates from the score nodes, diagnosis into the analyst slot, population size. */
function deriveRoundV2(lab: Lab, r: number, step: (s: string) => Ev[]) {
  const champ = step("champion").map((e) => e.champion).find((c) => c && c.expression);
  const done = step("population").length > 0;
  for (const e of [...step("score"), ...step("score_revised")]) {
    for (const c of e.candidates ?? []) {
      const ok = c.status === "ok";
      const isChamp = !!champ && champ.expression === c.expression;
      const reason = !ok ? `fit ${c.status}${c.reason && c.reason !== c.status ? `: ${c.reason}` : ""}`
        : !c.realizable ? "non-realizable (left the Lumley triangle)"
        : c.broken ? "broken: worse than SST on a held-out flow"
        : done && !isChamp ? "kept in or dropped from the population; not champion" : undefined;
      lab.candidates.push({ expr: c.expression, original: c.original ?? c.expression, round: r, group: e.group,
        stage: isChamp ? 6 : !ok ? 0 : c.realizable ? 5 : 1, status: isChamp ? "champion" : reason ? "rejected" : "alive",
        reason, mse: c.selection ?? undefined });
    }
  }
  if (champ) lab.champions.push({ round: r, ...champ });
  for (const e of step("diagnostician")) {
    lab.analyst.push({ round: r, regions: [], failure_regions: (e.failure_regions ?? []).map(String), next_hypothesis: e.next_hypothesis });
  }
  for (const e of step("population")) lab.population.push({ round: r, size: (e.population ?? []).length });
}

interface Store { session: string; events: Ev[]; connected: boolean; lastEventAt: number | null }
const Ctx = createContext<Store>({ session: "", events: [], connected: false, lastEventAt: null });

/** One socket per session for every view; reconnects after the server's ~1 s idle end, skipping what it holds. */
export function EventsProvider({ session, children }: { session: string; children: ReactNode }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  useEffect(() => {
    let seen = 0, stopped = false, timer: ReturnType<typeof setTimeout> | undefined, ws: WebSocket;
    setEvents([]); setLastEventAt(null);
    const connect = () => {
      ws = eventsSocket(session, "instant", seen);
      ws.onopen = () => setConnected(true);
      ws.onmessage = (m) => {
        let e: any;
        try { e = JSON.parse(String(m.data)); } catch { return; }
        if (e?.type === "end") return;
        const now = Date.now();
        const ev: Ev = { ...e, _i: seen++, _t: now };
        setEvents((prev) => [...prev, ev]);
        setLastEventAt(now);
      };
      ws.onclose = () => { setConnected(false); if (!stopped) timer = setTimeout(connect, 2000); };
    };
    connect();
    return () => { stopped = true; clearTimeout(timer); ws.close(); };
  }, [session]);
  return <Ctx.Provider value={{ session, events, connected, lastEventAt }}>{children}</Ctx.Provider>;
}

export function useEvents() { return useContext(Ctx); }

/** Lab model of the first `upto` events (Replay) or all of them (live). */
export function useLab(upto?: number): Lab {
  const { events } = useEvents();
  return useMemo(() => deriveLab(upto === undefined ? events : events.slice(0, upto)), [events, upto]);
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
