// Model Lab cockpit (S6.3): read-only. No physics in TypeScript.
import { useState } from "react";
import { CandidateInspector } from "./pages/CandidateInspector";
import { GeneralizationMatrix } from "./pages/GeneralizationMatrix";
import { MissionControl } from "./pages/MissionControl";
import { Replay } from "./pages/Replay";
import { Vault } from "./pages/Vault";

const VIEWS = ["Mission Control", "Generalization Matrix", "Candidate Inspector", "Vault", "Replay"] as const;
type View = (typeof VIEWS)[number];

export function App() {
  const [view, setView] = useState<View>("Mission Control");
  return (
    <main className="mx-auto max-w-6xl p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">FlowForge Model Lab</h1>
        <p className="text-sm text-neutral-600">Stream: ws://localhost:8000/ws/events (server-paced ~20/s).</p>
      </header>
      <nav className="flex flex-wrap gap-2" aria-label="Views">
        {VIEWS.map((v) => (
          <button key={v} onClick={() => setView(v)} className={`border px-3 py-1 text-sm ${view === v ? "bg-neutral-900 text-white" : "bg-white"}`}>{v}</button>
        ))}
      </nav>
      {view === "Mission Control" && <MissionControl />}
      {view === "Generalization Matrix" && <GeneralizationMatrix />}
      {view === "Candidate Inspector" && <CandidateInspector />}
      {view === "Vault" && <Vault />}
      {view === "Replay" && <Replay />}
    </main>
  );
}
