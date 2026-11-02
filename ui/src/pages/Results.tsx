import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Plotly from "plotly.js-dist-min";
import { fetchArms, type ArmsFile, type ArmSeedRow } from "../api/client";
import { Formula } from "../components/Formula";

const ARM_COLOR: Record<string, string> = { swarm: "#22d3ee", swarm_no_redteam: "#a78bfa", sparse_baseline: "#f97316" };
const DARK = { paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: "#cbd5e1", size: 11 }, margin: { l: 55, r: 10, t: 34, b: 50 } };

function Plot({ data, layout }: { data: unknown[]; layout: Record<string, unknown> }) {
  const ref = useRef<HTMLDivElement>(null);
  const key = JSON.stringify([data, layout]);
  useEffect(() => { if (ref.current) Plotly.react(ref.current, data, { ...DARK, ...layout }); }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);
  return <div ref={ref} className="w-full h-[320px]" />;
}

/** Elegance rule as plotted: among rows within 3% of the best worst-case ratio, the shortest DL. */
function eleganceChampion(rows: (ArmSeedRow & { arm: string })[]) {
  const ok = rows.filter((r) => typeof r.metric === "number" && typeof r.dl === "number");
  if (!ok.length) return undefined;
  const best = Math.min(...ok.map((r) => r.metric!));
  return ok.filter((r) => r.metric! <= best * 1.03).sort((a, b) => a.dl! - b.dl!)[0];
}

export function Results() {
  const q = useQuery({ queryKey: ["arms"], queryFn: fetchArms, refetchInterval: 15000 });
  const files = q.data ?? [];
  const [name, setName] = useState<string | null>(null);
  const run: ArmsFile | undefined = files.find((f) => f.file === name) ?? files.find((f) => !f.dry_run && f.mode === "frozen") ?? files[0];
  if (q.isError) return <p className="text-sm text-amber-300">API offline — start the FastAPI server.</p>;
  if (!run) return <p className="text-sm text-neutral-400">No arms results under runs/arms yet.</p>;

  const arms = Object.entries(run.arms);
  const rows = arms.flatMap(([arm, a]) => a.seeds.map((s) => ({ ...s, arm })));
  const champ = eleganceChampion(rows);
  const notReal = run.dry_run || run.mode !== "frozen";

  return (
    <section aria-label="Results" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">Experiment results</h2>
          <p className="text-xs text-neutral-400">{run.rounds} rounds × {run.groups} groups per session · spent ${run.spent_usd.toFixed(2)} of ${run.budget_usd} · {run.incomplete ? "INCOMPLETE" : "complete"}</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className={`px-2 py-0.5 rounded border font-mono ${notReal ? "border-amber-500 text-amber-300" : "border-emerald-600 text-emerald-300"}`}>
            {run.dry_run ? "DRY RUN — mocked agents, not a result" : `mode: ${run.mode} (a priori)`}
          </span>
          <select value={run.file} onChange={(e) => setName(e.target.value)} className="bg-neutral-900 text-neutral-300 rounded px-2 py-1 border border-white/10 font-mono">
            {files.map((f) => <option key={f.file} value={f.file}>{f.file}{f.dry_run ? " (dry)" : ""}</option>)}
          </select>
        </div>
      </div>

      <div className="glass-panel rounded-xl border border-white/10 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-neutral-400 border-b border-white/10">
            <tr><th className="text-left p-2">arm</th><th className="p-2">mean ± std</th><th className="p-2">session</th><th className="p-2">worst validation ratio</th><th className="p-2">DL</th><th className="p-2">$</th><th className="text-left p-2">champion</th></tr>
          </thead>
          <tbody>
            {arms.map(([arm, a]) => a.seeds.map((s, i) => (
              <tr key={arm + s.seed} className="border-b border-white/5 align-top">
                {i === 0 && <td rowSpan={a.seeds.length} className="p-2 font-semibold" style={{ color: ARM_COLOR[arm] }}>{arm}</td>}
                {i === 0 && <td rowSpan={a.seeds.length} className="p-2 text-center font-mono">{a.summary ? `${a.summary.mean.toFixed(3)} ± ${a.summary.stdev.toFixed(3)}` : "—"}</td>}
                <td className="p-2 text-center font-mono text-neutral-400">{s.seed}</td>
                <td className={`p-2 text-center font-mono font-semibold ${typeof s.metric === "number" && s.metric < 1 ? "text-emerald-300" : "text-rose-300"}`}>
                  {typeof s.metric === "number" ? s.metric.toFixed(3) : "—"}{s.no_champion ? " (no champion → SST)" : ""}</td>
                <td className="p-2 text-center font-mono text-neutral-400">{s.dl?.toFixed(0) ?? "—"}</td>
                <td className="p-2 text-center font-mono text-neutral-400">{(s.cost_usd ?? 0).toFixed(2)}</td>
                <td className="p-2 max-w-[420px] overflow-x-auto">{s.expression ? <Formula expr={s.expression} /> : "—"}</td>
              </tr>
            )))}
          </tbody>
        </table>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="glass-panel rounded-xl border border-white/10 p-2">
          <Plot data={[
            { type: "scatter", mode: "lines", name: "plain SST", x: [-0.5, arms.length - 0.5], y: [1, 1], line: { color: "#f87171", dash: "dash" }, hoverinfo: "skip" },
            ...arms.map(([arm, a], k) => ({ type: "scatter", mode: "markers", name: arm, x: a.seeds.map((_, j) => k + (j - 1) * 0.12),
              y: a.seeds.map((s) => s.metric), text: a.seeds.map((s) => `session ${s.seed}<br>${s.expression ?? ""}`), hoverinfo: "text+y",
              marker: { size: 14, color: ARM_COLOR[arm] ?? "#94a3b8", line: { color: "#0f172a", width: 1 } } })),
          ]} layout={{ title: { text: "Every session, every arm (lower is better)" }, showlegend: false,
            xaxis: { tickvals: arms.map((_, k) => k), ticktext: arms.map(([a]) => a), gridcolor: "#1e293b" },
            yaxis: { title: { text: "worst validation ratio" }, rangemode: "tozero", gridcolor: "#1e293b" } }} />
        </div>
        <div className="glass-panel rounded-xl border border-white/10 p-2">
          <Plot data={[
            ...arms.map(([arm, a]) => ({ type: "scatter", mode: "markers", name: arm, x: a.seeds.map((s) => s.dl), y: a.seeds.map((s) => s.metric),
              text: a.seeds.map((s) => s.expression ?? ""), hoverinfo: "text+x+y", marker: { size: 12, color: ARM_COLOR[arm] ?? "#94a3b8" } })),
            ...(champ ? [{ type: "scatter", mode: "markers", name: "elegance champion", x: [champ.dl], y: [champ.metric],
              marker: { size: 24, symbol: "star-open", color: "#facc15", line: { width: 2 } }, hoverinfo: "skip" }] : []),
          ]} layout={{ title: { text: "Accuracy vs simplicity (elegance rule: within 3% of best, shortest)" }, legend: { orientation: "h", y: -0.25 },
            xaxis: { title: { text: "description length (bits)" }, gridcolor: "#1e293b" },
            yaxis: { title: { text: "worst validation ratio" }, gridcolor: "#1e293b" } }} />
        </div>
      </div>

      {run.comparisons && (
        <div className="glass-panel rounded-xl border border-white/10 p-3 text-xs space-y-1">
          <div className="font-semibold text-neutral-300">Arm comparisons (one-sided, exact)</div>
          {Object.entries(run.comparisons).map(([k, v]) => (
            <div key={k} className="font-mono text-neutral-400">{k}: {Object.entries(v).map(([kk, vv]) => `${kk}=${typeof vv === "number" ? vv.toFixed(3) : vv}`).join(" · ")}</div>
          ))}
          <p className="text-neutral-500">With 3 sessions per arm the smallest possible p is 0.05: read effects and spread, not significance.</p>
        </div>
      )}
      <p className="text-[11px] text-neutral-500">All numbers are frozen-RANS a priori ratios (candidate error ÷ SST error). Locked-test results appear only in the Vault after a logged milestone.</p>
    </section>
  );
}
