// Mission Control: groups, budget meter, red-team feed. Read-only, zero physics.
import { useQuery } from "@tanstack/react-query";
import { fetchSessionState } from "../api/client";
import { EventFeed } from "../components/EventFeed";
import { StatusBadge } from "../components/StatusBadge";

export function MissionControl() {
  const q = useQuery({ queryKey: ["session"], queryFn: () => fetchSessionState() });
  return (
    <section aria-label="Mission control" className="space-y-3">
      <h2 className="text-xl font-semibold">Mission Control</h2>
      <StatusBadge ok={!!q.data?.exists} label={q.data ? `${q.data.event_count} events · paced ${q.data.events_per_second}/s` : "connecting"} />
      <p className="text-sm">Research groups, token budget, live red-team attack feed (validation flows only).</p>
      <EventFeed />
    </section>
  );
}
