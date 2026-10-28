import { useEffect, useRef, useState } from "react";
import { eventsSocket } from "../api/client";

interface EventItem {
  raw: string;
  parsed?: Record<string, any>;
  timestamp: string;
}

const ROLE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  board: { bg: "bg-purple-950/60", text: "text-purple-300", border: "border-purple-700/50" },
  theorist: { bg: "bg-cyan-950/60", text: "text-cyan-300", border: "border-cyan-700/50" },
  coder: { bg: "bg-emerald-950/60", text: "text-emerald-300", border: "border-emerald-700/50" },
  rung0: { bg: "bg-blue-950/60", text: "text-blue-300", border: "border-blue-700/50" },
  rung1: { bg: "bg-blue-950/60", text: "text-blue-300", border: "border-blue-700/50" },
  rung2: { bg: "bg-blue-950/60", text: "text-blue-300", border: "border-blue-700/50" },
  rung3: { bg: "bg-blue-950/60", text: "text-blue-300", border: "border-blue-700/50" },
  analyst: { bg: "bg-sky-950/60", text: "text-sky-300", border: "border-sky-700/50" },
  skeptic: { bg: "bg-amber-950/60", text: "text-amber-300", border: "border-amber-700/50" },
  redteam: { bg: "bg-rose-950/60", text: "text-rose-300", border: "border-rose-700/50" },
  composer: { bg: "bg-fuchsia-950/60", text: "text-fuchsia-300", border: "border-fuchsia-700/50" },
  champion: { bg: "bg-yellow-950/60", text: "text-yellow-300", border: "border-yellow-700/50" },
};

export function EventFeed({ session = "default" }: { session?: string }) {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = eventsSocket(session);
    ws.onmessage = (ev) => {
      const raw = String(ev.data);
      let parsed: Record<string, any> | undefined;
      try {
        parsed = JSON.parse(raw);
      } catch {
        // raw string
      }
      const item: EventItem = {
        raw,
        parsed,
        timestamp: new Date().toLocaleTimeString(),
      };
      setEvents((prev) => [...prev.slice(-99), item]);
    };
    return () => ws.close();
  }, [session]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return (
    <div className="glass-panel rounded-xl overflow-hidden border border-white/10">
      <div className="flex items-center justify-between px-4 py-3 bg-neutral-900/80 border-b border-white/10">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-semibold uppercase tracking-wider text-neutral-300">
            Live Stream Trace ({session})
          </span>
        </div>
        <span className="text-[11px] text-neutral-400 font-mono">
          {events.length} events logged · ~20/s
        </span>
      </div>

      <div className="p-3 space-y-2 max-h-[380px] overflow-y-auto font-mono text-xs">
        {events.length === 0 && (
          <div className="py-8 text-center text-neutral-500">
            Awaiting WebSocket event stream from FastAPI backend...
          </div>
        )}
        {events.map((e, idx) => {
          const role = e.parsed?.role || e.parsed?.step || e.parsed?.type || "info";
          const colors = ROLE_COLORS[role] || {
            bg: "bg-neutral-800/40",
            text: "text-neutral-300",
            border: "border-neutral-700/40",
          };

          const isExpanded = expandedIndex === idx;

          return (
            <div
              key={idx}
              className={`p-2 rounded-lg border transition-all ${colors.bg} ${colors.border} hover:border-white/20`}
            >
              <div
                className="flex items-center justify-between cursor-pointer select-none"
                onClick={() => setExpandedIndex(isExpanded ? null : idx)}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider ${colors.text} bg-black/40 border border-white/10`}
                  >
                    {role}
                  </span>
                  <span className="text-neutral-300 truncate max-w-[340px]">
                    {e.parsed?.summary ||
                      e.parsed?.candidate ||
                      e.parsed?.action ||
                      (e.parsed ? Object.keys(e.parsed).slice(0, 3).join(", ") : e.raw)}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[10px] text-neutral-500">
                  <span>{e.timestamp}</span>
                  <span className="text-neutral-400">{isExpanded ? "▲" : "▼"}</span>
                </div>
              </div>

              {isExpanded && (
                <div className="mt-2 pt-2 border-t border-white/10 text-[11px] text-neutral-300 overflow-x-auto">
                  <pre className="text-emerald-400/90 whitespace-pre-wrap">
                    {e.parsed ? JSON.stringify(e.parsed, null, 2) : e.raw}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
