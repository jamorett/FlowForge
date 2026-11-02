import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { controlRun, fetchRuns, startExperimentRun, startSessionRun, type RunInfo, type RunPreset } from "../api/client";

type Kind = "session" | "experiment";
interface Form { session: string; rounds: number; groups: number; redteam: boolean; mock: boolean; budget_usd: number;
  seeds: [number, number, number]; dry_run: boolean; archive_existing: boolean }

const STATUS_STYLE: Record<string, string> = {
  running: "text-emerald-300 border-emerald-600", paused: "text-amber-300 border-amber-600", stopping: "text-amber-300 border-amber-600",
  finished: "text-cyan-300 border-cyan-700", stopped: "text-neutral-300 border-neutral-600", budget: "text-amber-300 border-amber-700",
  failed: "text-rose-300 border-rose-600", killed: "text-rose-300 border-rose-600",
};
const ACTIVE = ["running", "paused", "stopping"];

function Num({ label, value, min, max, step = 1, onChange, hint }: { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 text-[11px] text-neutral-400" title={hint}>
      {label}
      <input type="number" value={value} min={min} max={max} step={step} onChange={(e) => onChange(Number(e.target.value))}
        className="bg-neutral-900 border border-white/10 rounded px-2 py-1 font-mono text-xs text-neutral-100 w-24" />
    </label>
  );
}
function Toggle({ label, checked, onChange, hint, danger = false }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string; danger?: boolean }) {
  return (
    <label className={`flex items-center gap-2 text-xs cursor-pointer ${danger && checked ? "text-amber-300" : "text-neutral-300"}`} title={hint}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="accent-cyan-500" />{label}
    </label>
  );
}

/** Start / steer runs from the cockpit: presets, session runs, the 3-arm experiment, pause/stop. */
export function RunPanel({ session, onWatch }: { session: string; onWatch: (s: string) => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["runs"], queryFn: fetchRuns, refetchInterval: 3000 });
  const [kind, setKind] = useState<Kind>("session");
  const [f, setF] = useState<Form>({ session, rounds: 1, groups: 1, redteam: true, mock: true, budget_usd: 1,
    seeds: [42, 43, 44], dry_run: true, archive_existing: false });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (p: Partial<Form>) => setF((x) => ({ ...x, ...p }));
  const lim = q.data?.limits;
  const live = kind === "session" ? !f.mock : !f.dry_run;
  const est = !live || !lim ? 0 : f.rounds * f.groups * (kind === "session" ? 1 : 6) * lim.usd_per_round_group;

  const applyPreset = (p: RunPreset) => {
    setKind(p.kind);
    set({ ...p.params, ...(p.kind === "session" ? { session: p.params.mock ? `${session}-mock` : `ui-${p.id}-${Date.now() % 100000}` } : {}) } as Partial<Form>);
    setMsg(`${p.label}: ${p.description}`);
  };

  async function start() {
    if (live && !window.confirm(`This run uses the real API and spends credits.\nEstimated ≈ $${est.toFixed(2)}, hard cap $${f.budget_usd.toFixed(2)}.\nStart it?`)) return;
    setBusy(true); setMsg(null);
    try {
      const res = kind === "session"
        ? await startSessionRun({ session: f.session, rounds: f.rounds, groups: f.groups, redteam: f.redteam, mock: f.mock, budget_usd: f.budget_usd, confirm_live: live })
        : await startExperimentRun({ rounds: f.rounds, groups: f.groups, seeds: f.seeds, budget_usd: f.budget_usd, dry_run: f.dry_run, archive_existing: f.archive_existing, confirm_live: live });
      if (res.status === "started" && res.run) {
        setMsg(`Started ${res.run.kind} run ${res.run.id}.`);
        onWatch(res.run.sessions[0]);
      } else {
        setMsg(`Not started: ${res.reason ?? res.status}`);
        if (res.needs_archive) set({ archive_existing: false });
      }
    } catch (e) {
      setMsg(`API error: ${e instanceof Error ? e.message : e}`);
    } finally { setBusy(false); qc.invalidateQueries({ queryKey: ["runs"] }); }
  }

  async function act(r: RunInfo, a: "pause" | "resume" | "stop" | "kill") {
    if (a === "kill" && !window.confirm("Kill the experiment now? No result file will be written.")) return;
    const res = await controlRun(r.id, a).catch((e) => ({ status: "error", reason: String(e) }));
    if (res.status !== "ok") setMsg(`${a} refused: ${res.reason}`);
    qc.invalidateQueries({ queryKey: ["runs"] });
  }

  const btn = "px-2 py-1 rounded text-[11px] font-semibold border border-white/10";
  return (
    <div className="glass-panel rounded-xl border border-cyan-500/20 p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-cyan-300">Run control</span>
        {q.isError && <span className="text-xs text-amber-300">API offline — start the FastAPI server</span>}
      </div>

      <div className="flex flex-wrap gap-2">
        {(q.data?.presets ?? []).map((p) => (
          <button key={p.id} onClick={() => applyPreset(p)} title={p.description}
            className={`${btn} ${p.params.mock || p.params.dry_run ? "bg-white/5 text-neutral-200" : "bg-amber-950/40 text-amber-200 border-amber-700/50"}`}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex gap-2 text-xs">
        {(["session", "experiment"] as Kind[]).map((k) => (
          <button key={k} onClick={() => setKind(k)} className={`${btn} ${kind === k ? "bg-cyan-700 text-white" : "bg-white/5 text-neutral-300"}`}>
            {k === "session" ? "Session run" : "3-arm experiment"}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-4">
        {kind === "session" && (
          <label className="flex flex-col gap-1 text-[11px] text-neutral-400">session
            <input value={f.session} onChange={(e) => set({ session: e.target.value })}
              className="bg-neutral-900 border border-white/10 rounded px-2 py-1 font-mono text-xs text-cyan-300 w-48" />
          </label>
        )}
        <Num label="rounds" value={f.rounds} min={1} max={lim?.max_rounds ?? 20} onChange={(v) => set({ rounds: v })} hint="rounds per session" />
        <Num label="groups / round" value={f.groups} min={1} max={lim?.max_groups ?? 4} onChange={(v) => set({ groups: v })} hint="parallel research groups; each adds a theorist call" />
        <Num label="budget cap $" value={f.budget_usd} min={0.1} max={lim?.session_dollar_limit ?? 50} step={0.5} onChange={(v) => set({ budget_usd: v })}
          hint="checked before every round (can overshoot by at most one round)" />
        {kind === "experiment" && f.seeds.map((s, i) => (
          <Num key={i} label={`session seed ${i + 1}`} value={s} min={0} max={99999}
            onChange={(v) => { const seeds = [...f.seeds] as Form["seeds"]; seeds[i] = v; set({ seeds }); }} />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-4">
        {kind === "session" ? (<>
          <Toggle label="red team on" checked={f.redteam} onChange={(v) => set({ redteam: v })} hint="off = ablation (RP1 contrast)" />
          <Toggle label="mock agents (free)" checked={f.mock} onChange={(v) => set({ mock: v })} hint="unticked = real API calls" />
        </>) : (<>
          <Toggle label="dry run (mocked agents, free)" checked={f.dry_run} onChange={(v) => set({ dry_run: v })} hint="bookkeeping only, never a result" />
          <Toggle label="archive existing sessions" checked={f.archive_existing} onChange={(v) => set({ archive_existing: v })}
            hint="moves old arms-* sessions to runs/_archive-*/ so their history cannot leak into this run" />
        </>)}
        <span className={`text-xs font-mono ${live ? "text-amber-300" : "text-emerald-300"}`}>
          {live ? `LIVE · est. ≈ $${est.toFixed(2)} (cap $${f.budget_usd.toFixed(2)})` : "free (mock / dry run)"}
        </span>
        <button onClick={start} disabled={busy || q.isError}
          className={`px-4 py-1.5 rounded-lg text-xs font-semibold text-white border disabled:opacity-50 ${live ? "bg-amber-600 border-amber-400/50" : "bg-gradient-to-r from-cyan-600 to-blue-600 border-cyan-400/40"}`}>
          {busy ? "Starting…" : kind === "session" ? `Start ${f.rounds}-round session` : "Start experiment"}
        </button>
      </div>
      {msg && <p className="text-[11px] text-neutral-400">{msg}</p>}

      {(q.data?.runs ?? []).length > 0 && (
        <div className="space-y-2">
          {q.data!.runs.slice(0, 6).map((r) => {
            const total = r.kind === "session" ? r.params.rounds : r.params.rounds * 6;
            const pct = Math.min(100, (r.spent_usd / r.params.budget_usd) * 100);
            const active = ACTIVE.includes(r.status);
            return (
              <div key={r.id} className="rounded-lg border border-white/10 bg-neutral-950/50 p-2 text-xs space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`px-1.5 py-0.5 rounded border font-mono text-[10px] uppercase ${STATUS_STYLE[r.status] ?? "text-neutral-400 border-white/10"}`}>{r.status}</span>
                  <span className="font-mono text-neutral-300">{r.kind} {r.id}</span>
                  <span className="text-neutral-500">
                    {r.kind === "session" ? `${r.rounds_done}/${total} rounds${r.round_now ? ` · round ${r.round_now} running` : ""}` : `${r.params.rounds}×${r.params.groups} per session · 6 swarm sessions + sparse`}
                    {r.params.mock || r.params.dry_run ? " · mock" : " · live"}{r.params.redteam === false ? " · no red team" : ""}
                  </span>
                  <span className="ml-auto flex gap-1">
                    {active && r.status !== "paused" && <button className={`${btn} bg-white/5 text-neutral-200`} onClick={() => act(r, "pause")}>⏸ pause</button>}
                    {r.status === "paused" && <button className={`${btn} bg-emerald-800 text-white`} onClick={() => act(r, "resume")}>▶ resume</button>}
                    {active && <button className={`${btn} bg-white/5 text-neutral-200`} onClick={() => act(r, "stop")}>⏹ stop</button>}
                    {active && r.kind === "experiment" && <button className={`${btn} bg-rose-900 text-white`} onClick={() => act(r, "kill")}>✕ kill now</button>}
                  </span>
                </div>
                <div className="h-1.5 rounded bg-neutral-800 overflow-hidden" title="spend vs budget cap (upper bound)">
                  <div className={`h-full ${pct >= 100 ? "bg-amber-500" : "bg-cyan-500"} transition-all`} style={{ width: `${pct}%` }} />
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-neutral-500">
                  <span className="font-mono">${r.spent_usd.toFixed(2)} / ${Number(r.params.budget_usd).toFixed(2)}</span>
                  {r.message && <span>· {r.message}</span>}
                  <span className="ml-auto flex flex-wrap gap-1">
                    {r.sessions.map((s) => (
                      <button key={s} onClick={() => onWatch(s)}
                        className={`px-1.5 py-0.5 rounded font-mono border ${s === session ? "border-cyan-500 text-cyan-300" : "border-white/10 text-neutral-400 hover:text-neutral-200"}`}>
                        watch {s.replace(/^(dryrun-)?arms-/, "")}
                      </button>
                    ))}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="text-[10px] text-neutral-500">Pause and stop act between rounds (a round is never cut in half); "kill now" ends an experiment immediately without a result file. Runs are tracked by this API server process.</p>
    </div>
  );
}
