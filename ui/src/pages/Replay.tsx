// Timeline scrubber over events.jsonl. Zero-token demo reproduction.
import { useState } from "react";
import { EventFeed } from "../components/EventFeed";

export function Replay() {
  const [session, setSession] = useState("default");
  return (
    <section aria-label="Replay" className="space-y-3">
      <h2 className="text-xl font-semibold">Replay</h2>
      <label className="text-sm">Session <input className="border px-2 py-1" value={session} onChange={(e) => setSession(e.target.value)} /></label>
      <p className="text-sm">Scrub the recorded session (server-paced ~20/s). Demo video is cut from here.</p>
      <EventFeed session={session || "default"} />
    </section>
  );
}
