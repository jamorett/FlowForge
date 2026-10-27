// Candidates x flows heatmap. Locked columns stay grey until milestone.
import { useQuery } from "@tanstack/react-query";
import { fetchMatrix } from "../api/client";
import { MatrixHeatmap } from "../components/MatrixHeatmap";

export function GeneralizationMatrix() {
  const q = useQuery({ queryKey: ["matrix"], queryFn: () => fetchMatrix() });
  return (
    <section aria-label="Generalization matrix" className="space-y-3">
      <h2 className="text-xl font-semibold">Generalization Matrix</h2>
      {q.isLoading && <p>Loading matrix…</p>}
      {q.error && <p className="text-sm">API offline — start the FastAPI server to load cells.</p>}
      {q.data && <MatrixHeatmap data={q.data} />}
    </section>
  );
}
