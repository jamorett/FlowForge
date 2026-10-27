import { useEffect, useState } from "react";
import { eventsSocket } from "../api/client";

// Live feed over the server-paced WebSocket (~20/s). Renders text only.
export function EventFeed({ session = "default" }: { session?: string }) {
  const [lines, setLines] = useState<string[]>([]);
  useEffect(() => {
    const ws = eventsSocket(session);
    ws.onmessage = (ev) => setLines((p) => [...p.slice(-49), String(ev.data)]);
    return () => ws.close();
  }, [session]);
  return <ul className="text-xs space-y-1 max-h-64 overflow-auto">{lines.map((l, i) => <li key={i} className="break-all border-b border-neutral-200 pb-1">{l}</li>)}{lines.length === 0 && <li>No events yet (server-paced ~20/s).</li>}</ul>;
}
