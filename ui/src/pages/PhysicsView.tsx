import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import { fetchMatrix, fetchPhysicsCases, fetchPhysicsView, fetchSessions, type MatrixData, type PhysicsView as View } from "../api/client";

// Read-only view of what a closure does to the turbulence state, from the frozen a-priori data.
// Lumley triangle: every point is one cell's anisotropy (corners: 1-, 2- and 3-component turbulence).
// The animation moves the RANS states by the candidate's correction; good closures land on the DNS cloud.

const TRIANGLE = { x: [0, 1, 0.5, 0], y: [0, 0, Math.sqrt(3) / 2, 0] };
const DARK = {
  paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#cbd5e1", size: 11 }, margin: { l: 40, r: 10, t: 30, b: 30 },
};

export function PhysicsView({ session }: { session: string }) {
  const [cases, setCases] = useState<Record<string, string[]>>({});
  const [caseId, setCaseId] = useState("periodic_hill_re5600");
  const [candidates, setCandidates] = useState<string[]>([]);
  const [source, setSource] = useState(session);
  const [expression, setExpression] = useState("0");
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [t, setT] = useState(0);
  const triRef = useRef<HTMLDivElement>(null);
  const geoRef = useRef<HTMLDivElement>(null);
  const profRef = useRef<HTMLDivElement>(null);
  const anim = useRef<number | null>(null);

  useEffect(() => {
    fetchPhysicsCases().then(setCases).catch(() => setError("API offline"));
  }, []);

  useEffect(() => {
    let current = true;
    const pick = (m: MatrixData) => {
      const list = (m.candidates ?? []).filter(Boolean);
      // Default to the candidate with the lowest logged error (fall back to the first one).
      const scored = (m.cells ?? []).filter((c) => c.error !== null && list.includes(c.candidate));
      const best = scored.sort((a, b) => (a.error as number) - (b.error as number))[0]?.candidate;
      return { list, best: best ?? list[0], scored: scored.length };
    };
    (async () => {
      let found = pick(await fetchMatrix(session));
      let from = session;
      // A session without scored candidates (e.g. a fresh round): borrow the newest session that has some.
      if (!found.scored) {
        for (const s of await fetchSessions()) {
          if (s.session === session) continue;
          const other = pick(await fetchMatrix(s.session));
          if (other.scored) { found = other; from = s.session; break; }
        }
      }
      if (!current) return;
      setCandidates(found.list);
      setSource(from);
      if (found.best) setExpression(found.best);
    })().catch(() => current && setCandidates([]));
    return () => {
      current = false;
    };
  }, [session]);

  useEffect(() => {
    // Ignore responses of superseded requests (typing, or the default switching to the best candidate).
    let current = true;
    setError(null);
    fetchPhysicsView(expression, caseId)
      .then((v) => {
        if (!current) return;
        if (v.error) setError(v.error);
        else {
          setView(v);
          setT(0);
        }
      })
      .catch((e) => current && setError(String(e)));
    return () => {
      current = false;
    };
  }, [expression, caseId]);

  // Draw both plots when the data changes.
  useEffect(() => {
    if (!view || !triRef.current || !geoRef.current) return;
    const marker = (color: string, size = 3, opacity = 0.55) => ({ color, size, opacity });
    Plotly.newPlot(triRef.current, [
      { x: TRIANGLE.x, y: TRIANGLE.y, mode: "lines", line: { color: "#475569" }, hoverinfo: "skip", name: "realizable" },
      { x: view.dns.x, y: view.dns.y, mode: "markers", marker: marker("#22d3ee", 3, 0.35), name: "DNS (truth)" },
      { x: view.rans.x, y: view.rans.y, mode: "markers", marker: marker("#f59e0b"), name: "RANS + correction" },
    ], { ...DARK, title: { text: "Lumley triangle" }, xaxis: { visible: false }, yaxis: { visible: false, scaleanchor: "x" },
      legend: { orientation: "h", y: -0.05 } });
    const g = view.geometry;
    const lim = Math.max(...g.gain.map(Math.abs)) || 1;
    Plotly.newPlot(geoRef.current, [
      { x: g.x, y: g.y, mode: "markers", type: "scattergl", name: "gain",
        // gain > 0 means the closure reduced the error at that point: blue; < 0 (worse): red.
        marker: { size: 4, color: g.gain, colorscale: "RdBu", reversescale: true, cmin: -lim, cmax: lim,
          colorbar: { title: { text: "helps ↑ / hurts ↓", side: "right" }, tickfont: { color: "#94a3b8" } } } },
    ], { ...DARK, title: { text: "Where the closure helps (blue) or hurts (red)" },
      yaxis: { scaleanchor: "x", gridcolor: "#1e293b" }, xaxis: { gridcolor: "#1e293b" } });
    if (profRef.current && view.b12) {
      // b12 (shear anisotropy) vs height at 4 stations, drawn offset at each station: x = station + SCALE * b12.
      const SCALE = 8;
      const xmin = Math.min(...g.x), xmax = Math.max(...g.x), span = xmax - xmin;
      const stations = [0.1, 0.35, 0.6, 0.85].map((f) => xmin + f * span);
      const series = [["dns", "DNS (truth)", "#22d3ee"], ["rans", "RANS (SST)", "#f59e0b"], ["corrected", "RANS + candidate", "#f8fafc"]] as const;
      const traces: unknown[] = [];
      stations.forEach((xs, k) => {
        const pts = g.x.map((x, i) => i).filter((i) => Math.abs(g.x[i] - xs) < span / 60).sort((a, b) => g.y[a] - g.y[b]);
        for (const [key, label, color] of series) {
          traces.push({ x: pts.map((i) => xs + SCALE * view.b12![key][i]), y: pts.map((i) => g.y[i]), mode: "lines+markers",
            type: "scatter", name: label, legendgroup: key, showlegend: k === 0, line: { color, width: key === "dns" ? 3 : 1.5 },
            marker: { size: 3, color }, hovertemplate: `${label}<br>x≈${xs.toFixed(2)} y=%{y:.3f}<extra></extra>` });
        }
        traces.push({ x: [xs, xs], y: [Math.min(...g.y), Math.max(...g.y)], mode: "lines", line: { color: "#334155", dash: "dot" }, hoverinfo: "skip", showlegend: false });
      });
      Plotly.newPlot(profRef.current, traces, { ...DARK, title: { text: `Equation vs reality: b₁₂ profiles at 4 stations (offset ×${SCALE})` },
        xaxis: { title: { text: "x  (station + scaled b₁₂)" }, gridcolor: "#1e293b" }, yaxis: { title: { text: "y" }, gridcolor: "#1e293b" },
        legend: { orientation: "h", y: -0.18 } });
    }
    return () => {
      if (triRef.current) Plotly.purge(triRef.current);
      if (geoRef.current) Plotly.purge(geoRef.current);
      if (profRef.current) Plotly.purge(profRef.current);
    };
  }, [view]);

  // Interpolate RANS -> corrected for the current animation time.
  useEffect(() => {
    if (!view || !triRef.current) return;
    const mix = (a: number[], b: number[]) => a.map((v, i) => v + t * (b[i] - v));
    Plotly.restyle(triRef.current, { x: [mix(view.rans.x, view.corrected.x)], y: [mix(view.rans.y, view.corrected.y)] }, [2]);
  }, [t, view]);

  const play = () => {
    if (anim.current) cancelAnimationFrame(anim.current);
    const start = performance.now();
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / 2500);
      setT(p);
      if (p < 1) anim.current = requestAnimationFrame(step);
    };
    anim.current = requestAnimationFrame(step);
  };

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-xl p-4 space-y-3 text-sm">
        <h2 className="text-lg font-semibold">Physics view</h2>
        <p className="text-neutral-400 text-xs">
          A-priori (frozen) data. Amber points start at the RANS turbulence state and move by the closure's correction;
          a good closure brings them onto the cyan DNS cloud.
        </p>
        <div className="flex flex-wrap gap-3 items-center">
          <select value={caseId} onChange={(e) => setCaseId(e.target.value)}
            className="bg-neutral-900 border border-white/10 rounded px-2 py-1 font-mono text-xs">
            {Object.entries(cases).map(([split, ids]) => (
              <optgroup key={split} label={split}>
                {ids.map((id) => <option key={id} value={id}>{id}</option>)}
              </optgroup>
            ))}
          </select>
          <input list="physics-candidates" value={expression} onChange={(e) => setExpression(e.target.value)}
            className="flex-1 min-w-[320px] bg-neutral-900 border border-white/10 rounded px-2 py-1 font-mono text-xs" />
          <datalist id="physics-candidates">
            {candidates.map((c) => <option key={c} value={c} />)}
          </datalist>
          <button onClick={play} className="px-3 py-1 rounded bg-cyan-700 hover:bg-cyan-600 text-xs font-semibold">
            ▶ Apply correction
          </button>
          <input type="range" min={0} max={1} step={0.01} value={t} onChange={(e) => setT(Number(e.target.value))} />
          {view && view.ratio !== null && (
            <span className="font-mono text-xs">
              error vs no correction: <b className={view.ratio < 1 ? "text-emerald-400" : "text-rose-400"}>{view.ratio.toFixed(3)}</b>
            </span>
          )}
        </div>
        {source !== session && (
          <p className="text-neutral-500 text-xs">Session "{session}" has no scored candidates yet; showing candidates from "{source}".</p>
        )}
        {error && <p className="text-rose-400 text-xs">{error}</p>}
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div ref={triRef} className="glass-panel rounded-xl h-[420px]" />
        <div ref={geoRef} className="glass-panel rounded-xl h-[420px]" />
      </div>
      <div ref={profRef} className="glass-panel rounded-xl h-[440px]" />
    </div>
  );
}
