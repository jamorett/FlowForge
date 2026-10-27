import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import type { MatrixData } from "../api/client";

// Plotly heatmap of backend-supplied errors. Locked columns greyed. Display only.
export function MatrixHeatmap({ data }: { data: MatrixData }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const flows = [...data.flows.train, ...data.flows.generated.map((g) => g.flow), ...data.flows.locked];
    const z = data.candidates.map((c) => flows.map((f) => data.cells.find((x) => x.candidate === c && x.flow === f)?.error ?? null));
    void Plotly.newPlot(ref.current, [{ type: "heatmap", x: flows, y: data.candidates, z, colorscale: "Viridis" }], { margin: { t: 20, l: 120 }, height: 320 });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [data]);
  if (data.candidates.length === 0) return <p className="text-sm text-neutral-600">No scored candidates in this session yet. Generated attack flows: {data.flows.generated.length} (validation only).</p>;
  return <div ref={ref} />;
}
