import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import type { MatrixData } from "../api/client";

export function MatrixHeatmap({ data }: { data: MatrixData }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const flows = [
      ...data.flows.train,
      ...data.flows.generated.map((g) => g.flow),
      ...data.flows.locked,
    ];
    const z = data.candidates.map((c) =>
      flows.map((f) => data.cells.find((x) => x.candidate === c && x.flow === f)?.error ?? null)
    );

    const layout: Record<string, any> = {
      margin: { t: 30, r: 20, b: 70, l: 140 },
      height: Math.max(300, data.candidates.length * 40 + 120),
      paper_bgcolor: "transparent",
      plot_bgcolor: "rgba(15, 23, 42, 0.4)",
      font: { color: "#94a3b8", family: "Inter, sans-serif", size: 11 },
      xaxis: {
        tickangle: -30,
        gridcolor: "rgba(255, 255, 255, 0.05)",
      },
      yaxis: {
        gridcolor: "rgba(255, 255, 255, 0.05)",
      },
    };

    void (Plotly as any).newPlot(
      ref.current,
      [
        {
          type: "heatmap",
          x: flows,
          y: data.candidates,
          z,
          colorscale: "Viridis",
          colorbar: {
            title: { text: "Error vs SST", side: "top" },
            tickfont: { color: "#94a3b8" },
          },
        },
      ],
      layout,
      { responsive: true, displayModeBar: false }
    );

    return () => {
      if (ref.current) Plotly.purge(ref.current);
    };
  }, [data]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div className="glass-panel p-3 rounded-lg border-l-4 border-emerald-500">
          <div className="text-neutral-400 font-medium">Training Flows</div>
          <div className="text-emerald-300 font-bold text-sm mt-0.5">
            {data.flows.train.length} cases
          </div>
          <div className="text-[11px] text-neutral-500 truncate mt-1">
            {data.flows.train.join(", ")}
          </div>
        </div>

        <div className="glass-panel p-3 rounded-lg border-l-4 border-amber-500">
          <div className="text-neutral-400 font-medium">Red Team Attacks (Validation)</div>
          <div className="text-amber-300 font-bold text-sm mt-0.5">
            {data.flows.generated.length} attack flows
          </div>
          <div className="text-[11px] text-neutral-500 mt-1">Slopes [0.5–1.5], sweeps</div>
        </div>

        <div className="glass-panel p-3 rounded-lg border-l-4 border-neutral-600">
          <div className="text-neutral-400 font-medium">Locked Test Set</div>
          <div className="text-neutral-300 font-bold text-sm mt-0.5">
            {data.flows.locked.length} cases (Greyed)
          </div>
          <div className="text-[11px] text-neutral-500 truncate mt-1">
            {data.flows.locked.join(", ")}
          </div>
        </div>
      </div>

      <div className="glass-panel p-4 rounded-xl border border-white/10 overflow-hidden">
        {data.candidates.length === 0 ? (
          <div className="py-12 text-center text-neutral-500">
            No candidates evaluated yet in this session. Start a round to populate the generalization matrix.
          </div>
        ) : (
          <div ref={ref} className="w-full" />
        )}
      </div>
    </div>
  );
}
