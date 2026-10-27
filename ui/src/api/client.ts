// Read-only API client. Zero physics: display data only, never compute closures.
export interface SessionState { session: string; exists: boolean; event_count: number; event_types: Record<string, number>; pace_seconds: number; events_per_second: number }
export interface MatrixData { session: string; candidates: string[]; flows: { train: string[]; generated: { flow: string; alpha: number; reynolds: number; split: string }[]; locked: string[] }; locked_greyed: boolean; cells: { candidate: string; flow: string; error: number | null; split: string }[] }

const base = import.meta.env.VITE_API ?? "http://localhost:8000";
export async function fetchSessionState(session = "default"): Promise<SessionState> {
  const r = await fetch(`${base}/api/session/state?session=${encodeURIComponent(session)}`);
  if (!r.ok) throw new Error(`session state ${r.status}`);
  return r.json() as Promise<SessionState>;
}
export async function fetchMatrix(session = "default"): Promise<MatrixData> {
  const r = await fetch(`${base}/api/matrix?session=${encodeURIComponent(session)}`);
  if (!r.ok) throw new Error(`matrix ${r.status}`);
  return r.json() as Promise<MatrixData>;
}
export function eventsSocket(session = "default"): WebSocket {
  const wsBase = base.replace(/^http/, "ws");
  return new WebSocket(`${wsBase}/ws/events?session=${encodeURIComponent(session)}`);
}
