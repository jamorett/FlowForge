import { useState } from "react";
import { artifactUrl } from "../api/client";
import { Formula } from "./Formula";
import type { Champion, Lab } from "../state/events";

const fmt = (v?: number) => (typeof v === "number" ? v.toFixed(3) : "—");
const tone = (v?: number) => (typeof v !== "number" ? "text-neutral-500" : v < 1 ? "text-emerald-300" : "text-rose-300");

function Ratio({ label, v }: { label: string; v?: number }) {
  return (
    <div className="flex justify-between gap-3 text-xs">
      <span className="text-neutral-400 truncate">{label}</span>
      <span className={`font-mono font-semibold ${tone(v)}`}>{fmt(v)}</span>
    </div>
  );
}

export function ChampionCard({ champ, title = "Best champion" }: { champ?: Champion; title?: string }) {
  if (!champ) return <div className="glass-panel rounded-xl border border-white/10 p-4 text-xs text-neutral-500">No champion yet — every candidate so far was rejected or the round is still running.</div>;
  return (
    <div className="glass-panel rounded-xl border border-yellow-500/30 p-4 space-y-3">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold uppercase tracking-wider text-yellow-300">{title} · round {champ.round}</span>
        <span className="px-2 py-0.5 rounded border border-white/10 bg-neutral-900 text-neutral-400 font-mono">frozen · a priori</span>
      </div>
      <div className="overflow-x-auto"><Formula expr={champ.expression} block /></div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1">
        <Ratio label="worst validation (headline)" v={champ.worst_validation_ratio} />
        <Ratio label="train" v={champ.train?.ratio} />
        {Object.entries(champ.validation ?? {}).map(([k, v]) => <Ratio key={k} label={`validation · ${k}`} v={v?.ratio} />)}
        {Object.entries(champ.attack_ratios ?? {}).map(([k, v]) => <Ratio key={k} label={`attack · ${k.replace("periodic_hill_", "")}`} v={v} />)}
        <div className="flex justify-between text-xs"><span className="text-neutral-400">description length</span><span className="font-mono">{champ.dl?.toFixed(1) ?? "—"} bits</span></div>
      </div>
      <p className="text-[11px] text-neutral-500">Ratios = candidate error ÷ plain-SST error on frozen-RANS data; below 1.0 beats SST.</p>
    </div>
  );
}

/** Attack hills the red team throws at champions, and how the latest champion fares on each. */
export function RedTeamArena({ lab, redteamEnabled = true }: { lab: Lab; redteamEnabled?: boolean }) {
  const latest = [...lab.champions].reverse().find((c) => c.attack_ratios && Object.keys(c.attack_ratios).length);
  const byCase = new Map<string, { failure?: string; alpha?: number }>();
  for (const a of lab.attacks) if (a.case_id && !byCase.has(a.case_id)) byCase.set(a.case_id, a);
  const cases = [...new Set([...byCase.keys(), ...Object.keys(latest?.attack_ratios ?? {})])];
  return (
    <div className="glass-panel rounded-xl border border-rose-500/30 p-4 space-y-3">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold uppercase tracking-wider text-rose-300">Red team arena</span>
        <span className="font-mono text-neutral-400">{lab.attacks.length} attacks · {lab.breaks.length} breaks</span>
      </div>
      {!cases.length && <p className="text-xs text-neutral-500">{redteamEnabled ? "No attacks logged yet in this session." : "Red team disabled in this arm (ablation) — no attacks by design."}</p>}
      <div className="grid sm:grid-cols-3 gap-3">
        {cases.map((cid) => {
          const r = latest?.attack_ratios?.[cid];
          const broken = typeof r === "number" && r >= 1;
          const meta = byCase.get(cid);
          return (
            <div key={cid} className={`rounded-lg border p-3 bg-neutral-950/60 ${broken ? "border-rose-500 animate-pulse" : "border-white/10"}`}>
              <div className="text-xs font-mono text-neutral-200">{cid.replace("periodic_hill_", "hill ")}</div>
              {meta?.alpha !== undefined && <div className="text-[10px] text-neutral-500">steepness α = {meta.alpha}</div>}
              <div className="mt-2 h-2 rounded bg-neutral-800 relative overflow-hidden" title="bar = champion error ÷ SST error; red line = SST">
                <div className={`h-full ${broken ? "bg-rose-500" : "bg-emerald-400"} transition-all duration-700`} style={{ width: `${Math.min(100, ((r ?? 0) / 1.5) * 100)}%` }} />
                <div className="absolute top-0 bottom-0 w-0.5 bg-red-400" style={{ left: `${100 / 1.5}%` }} />
              </div>
              <div className={`mt-1 text-xs font-mono ${tone(r)}`}>{typeof r === "number" ? `${r.toFixed(3)} × SST ${broken ? "· BROKEN" : "· holds"}` : "not scored yet"}</div>
              {meta?.failure && <p className="mt-1 text-[10px] text-neutral-500 line-clamp-3" title={meta.failure}>{meta.failure}</p>}
            </div>
          );
        })}
      </div>
      {lab.breaks.length > 0 && (
        <ul className="text-[11px] text-rose-200 font-mono space-y-0.5 max-h-24 overflow-y-auto">
          {lab.breaks.slice(-6).map((b, i) => <li key={i}>r{b.round} broke {b.case_id ?? "?"} ({fmt(b.ratio)}): {b.expression}</li>)}
        </ul>
      )}
    </div>
  );
}

/** Analyst error map with SAM 3.1 regions; the source label is never upgraded. */
export function SamPanel({ lab, session }: { lab: Lab; session: string }) {
  const rounds = lab.analyst.filter((a) => a.image);
  const [pick, setPick] = useState<number | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null); // hooks before any early return
  const a = rounds.find((x) => x.round === pick) ?? rounds[rounds.length - 1];
  if (!a) return <div className="glass-panel rounded-xl border border-white/10 p-4 text-xs text-neutral-500">No analyst error map yet in this session.</div>;
  const spatial = a.regions.some((r: any) => Array.isArray(r.x_range)); // pre-fix maps were not spatial
  const W = size?.w ?? 121, H = size?.h ?? 121;
  return (
    <div className="glass-panel rounded-xl border border-sky-500/30 p-4 space-y-3">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold uppercase tracking-wider text-sky-300">Where it fails · Analyst + SAM</span>
        <span className="flex items-center gap-2">
          <select value={a.round} onChange={(e) => setPick(Number(e.target.value))} className="bg-neutral-900 text-neutral-300 rounded px-1 border border-white/10">
            {rounds.map((r) => <option key={r.round} value={r.round}>round {r.round}</option>)}
          </select>
          <span className={`px-2 py-0.5 rounded border font-mono ${a.source === "sam-3.1" ? "border-cyan-600 text-cyan-300" : "border-white/10 text-neutral-400"}`}>
            source: {a.source ?? "none"}
          </span>
        </span>
      </div>
      {!spatial && (
        <p className="text-[11px] text-amber-300">Legacy error map (recorded before 2026-11-01 fix): cells were not spatially arranged, so these regions do not correspond to places in the flow.</p>
      )}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="relative w-full" style={{ aspectRatio: `${W} / ${H}` }}>
          <img src={artifactUrl(session, a.image!)} alt={`error map round ${a.round}`} onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            className="absolute inset-0 w-full h-full rounded [image-rendering:pixelated]" />
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 w-full h-full">
            {a.regions.map((r: any, i: number) => {
              const [x0, y0, x1, y1] = r.box ?? [0, 0, 0, 0];
              return (
                <g key={i}>
                  <rect x={x0} y={y0} width={Math.max(1, x1 - x0)} height={Math.max(1, y1 - y0)} fill="none" stroke="#22d3ee" strokeWidth={W / 150} strokeDasharray={`${W / 60} ${W / 90}`} />
                  <text x={x0 + 2} y={y0 + W / 30} fontSize={W / 28} fill="#22d3ee">{r.region}</text>
                </g>
              );
            })}
          </svg>
        </div>
        <div className="space-y-2 text-xs">
          {a.regions.map((r: any, i: number) => (
            <div key={i} className="font-mono text-neutral-300">{r.region}: mean {fmt(r.mean_error)} · max {fmt(r.max_error)}{r.severity ? ` · ${r.severity}` : ""}</div>
          ))}
          <div className="text-neutral-400 space-y-1 max-h-40 overflow-y-auto">
            {a.failure_regions.slice(0, 3).map((t, i) => <p key={i}>• {t}</p>)}
          </div>
          {a.next_hypothesis && <p className="text-sky-200"><span className="text-neutral-500">next hypothesis: </span>{a.next_hypothesis}</p>}
        </div>
      </div>
    </div>
  );
}
