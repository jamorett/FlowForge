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
export interface RegionsData { image: string | null; source: string; model: string | null; regions: { region: string; box: number[]; max_error?: number; mean_error?: number; severity?: string; source?: string }[]; detail: string }
export interface StartRoundResult { status: string; session?: string; mock?: boolean; events?: string; reason?: string }
export async function startRound(session = "default", mock = true): Promise<StartRoundResult> {
  const r = await fetch(`${base}/api/rounds/start?session=${encodeURIComponent(session)}&mock=${mock ? "true" : "false"}`, { method: "POST" });
  if (!r.ok) throw new Error(`start round ${r.status}`);
  return r.json() as Promise<StartRoundResult>;
}
export async function fetchLatestRegions(session = "default", useApi = false): Promise<RegionsData> {
  const r = await fetch(`${base}/api/latest_regions?session=${encodeURIComponent(session)}&use_api=${useApi ? "true" : "false"}`);
  if (!r.ok) throw new Error(`latest regions ${r.status}`);
  return r.json() as Promise<RegionsData>;
}
