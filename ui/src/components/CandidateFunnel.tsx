import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import { STAGES, type Lab } from "../state/events";

const DARK = { paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: "#cbd5e1", size: 11 },
  margin: { l: 50, r: 10, t: 34, b: 60 } };
const STATUS_COLOR = { alive: "#22d3ee", rejected: "#64748b", champion: "#facc15" } as const;

function usePlot(data: unknown[], layout: Record<string, unknown>) {
  const ref = useRef<HTMLDivElement>(null);
  const key = JSON.stringify(data);
  useEffect(() => { if (ref.current) Plotly.react(ref.current, data, { ...DARK, ...layout }); }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);
  return ref;
}

/** Every candidate placed at the furthest ladder stage it reached, per round. */
export function CandidateFunnel({ lab }: { lab: Lab }) {
  const traces = (["rejected", "alive", "champion"] as const).map((st) => {
    const cs = lab.candidates.map((c, i) => ({ c, i })).filter(({ c }) => c.status === st);
    return {
      type: "scatter", mode: "markers", name: st,
      x: cs.map(({ c, i }) => c.stage + ((i * 0.137) % 0.5) - 0.25),
      y: cs.map(({ c, i }) => c.round + ((i * 0.291) % 0.6) - 0.3),
      text: cs.map(({ c }) => `${c.expr}<br>${c.group ?? ""} · ${STAGES[c.stage]}${c.reason ? `<br><b>${c.reason}</b>` : ""}` +
        (c.mse !== undefined ? `<br>train MSE ${c.mse.toExponential(2)}` : "")),
      hoverinfo: "text",
      marker: { color: STATUS_COLOR[st], size: st === "champion" ? 16 : 9, symbol: st === "champion" ? "star" : "circle",
        line: { color: "#0f172a", width: 1 }, opacity: st === "rejected" ? 0.6 : 0.95 },
    };
  });
  const ref = usePlot(traces, {
    title: { text: `Candidate funnel · ${lab.candidates.length} proposals` }, showlegend: true,
    legend: { orientation: "h", y: -0.28 }, hovermode: "closest",
    xaxis: { tickvals: STAGES.map((_, i) => i), ticktext: STAGES, range: [-0.5, 6.5], gridcolor: "#1e293b" },
    yaxis: { title: { text: "round" }, dtick: 1, autorange: "reversed", gridcolor: "#1e293b" },
  });
  return <div ref={ref} className="w-full h-[320px]" />;
}

/** Champion worst-case validation ratio per round vs plain SST (1.0). */
export function ProgressChart({ lab }: { lab: Lab }) {
  const ch = lab.champions.filter((c) => typeof c.worst_validation_ratio === "number");
  const rounds = lab.rounds.length ? lab.rounds : [1];
  const ref = usePlot([
    { type: "scatter", mode: "lines", name: "plain SST", x: [Math.min(...rounds) - 0.3, Math.max(...rounds) + 0.3], y: [1, 1],
      line: { color: "#f87171", dash: "dash" }, hoverinfo: "skip" },
    { type: "scatter", mode: "lines+markers", name: "round champion", x: ch.map((c) => c.round), y: ch.map((c) => c.worst_validation_ratio),
      text: ch.map((c) => c.expression), hovertemplate: "round %{x}: %{y:.3f}<br>%{text}<extra></extra>",
      line: { color: "#facc15" }, marker: { size: 10, color: "#facc15" } },
  ], {
    title: { text: "How are we doing? (lower is better, frozen)" }, showlegend: true, legend: { orientation: "h", y: -0.3 },
    xaxis: { title: { text: "round" }, dtick: 1, gridcolor: "#1e293b" },
    yaxis: { title: { text: "worst validation ratio" }, gridcolor: "#1e293b", rangemode: "tozero" },
  });
  return <div ref={ref} className="w-full h-[320px]" />;
}

const FAMILIES = ["polynomial", "tanh", "rational (div)", "exp / sqrt", "mixed"];
function family(expr: string): string {
  const f = ["tanh", "div", "exp", "sqrt"].filter((k) => expr.includes(`${k}(`));
  if (!f.length) return "polynomial";
  if (f.length > 1) return "mixed";
  return f[0] === "tanh" ? "tanh" : f[0] === "div" ? "rational (div)" : "exp / sqrt";
}
const tensors = (expr: string) => ["T1", "T2", "T3"].filter((t) => expr.includes(t)).join("+") || "scalar (T1)";

/** Where the agents search: proposals grouped by tensor set × coefficient family. */
export function ClusterView({ lab }: { lab: Lab }) {
  const groups = new Map<string, { fam: string; ts: string; n: number; best?: number; champ: boolean; ex: string[] }>();
  for (const c of lab.candidates) {
    const fam = family(c.expr), ts = tensors(c.expr), key = `${fam}|${ts}`;
    const g = groups.get(key) ?? { fam, ts, n: 0, champ: false, ex: [] };
    g.n += 1;
    if (c.mse !== undefined && (g.best === undefined || c.mse < g.best)) g.best = c.mse;
    if (c.status === "champion") g.champ = true;
    if (g.ex.length < 3) g.ex.push(c.expr);
    groups.set(key, g);
  }
  const gs = [...groups.values()];
  const tsList = [...new Set(gs.map((g) => g.ts))].sort();
  const maxN = Math.max(1, ...gs.map((g) => g.n));
  const ref = usePlot([
    { type: "scatter", mode: "markers", name: "structure family",
      x: gs.map((g) => FAMILIES.indexOf(g.fam)), y: gs.map((g) => tsList.indexOf(g.ts)),
      text: gs.map((g) => `<b>${g.fam} · ${g.ts}</b><br>${g.n} proposals${g.champ ? " · produced a champion" : ""}` +
        (g.best !== undefined ? `<br>best train MSE ${g.best.toExponential(2)}` : "") + `<br>${g.ex.join("<br>")}`),
      hoverinfo: "text",
      marker: { size: gs.map((g) => 14 + 46 * Math.sqrt(g.n / maxN)), sizemode: "diameter",
        color: gs.map((g) => (g.best !== undefined ? Math.log10(g.best) : null)), colorscale: "Viridis", reversescale: true,
        showscale: true, colorbar: { title: { text: "log10 best MSE", side: "right" }, tickfont: { color: "#94a3b8" } },
        line: { color: gs.map((g) => (g.champ ? "#facc15" : "#0f172a")), width: gs.map((g) => (g.champ ? 3 : 1)) }, opacity: 0.9 } },
  ], {
    title: { text: "Where the agents search (bubble = # proposals, gold ring = produced a champion)" }, showlegend: false, hovermode: "closest",
    xaxis: { tickvals: FAMILIES.map((_, i) => i), ticktext: FAMILIES, range: [-0.6, FAMILIES.length - 0.4], gridcolor: "#1e293b" },
    yaxis: { tickvals: tsList.map((_, i) => i), ticktext: tsList, range: [-0.6, Math.max(tsList.length, 1) - 0.4], gridcolor: "#1e293b" },
  });
  return <div ref={ref} className="w-full h-[320px]" />;
}
