// Equation (KaTeX), profiles vs DNS/SST, barycentric map, error map. Display only.
import { EquationView } from "../components/EquationView";

export function CandidateInspector() {
  return (
    <section aria-label="Candidate inspector" className="space-y-3">
      <h2 className="text-xl font-semibold">Candidate Inspector</h2>
      <EquationView tex={"a^{\\Delta}_{ij} = \\sigma(w I + b)\\,a^{(M_1)}_{ij} + (1-\\sigma(w I + b))\\,a^{(M_2)}_{ij}"} />
      <p className="text-sm">Velocity profiles, barycentric map and attack history are rendered from backend fields; no tensor algebra runs in React.</p>
      <p className="text-xs">Gate cost: +16 bits per active gate.</p>
    </section>
  );
}
