// Read-only API client. Zero physics: display data only, never compute closures.
export interface SessionState { session: string; exists: boolean; event_count: number; event_types: Record<string, number>; pace_seconds: number; events_per_second: number;
  tokens: number; dollars_upper: number; rounds: number[]; last_step: string | null }
export interface MatrixData { session: string; candidates: string[]; flows: { train: string[]; generated: { flow: string; alpha: number; reynolds: number; split: string }[]; locked: string[] }; locked_greyed: boolean; cells: { candidate: string; flow: string; error: number | null; split: string }[] }

// Default: same origin, forwarded to the API by the Vite dev proxy (vite.config.ts), so the UI
// works on any dev port without CORS. Set VITE_API to call an API directly instead.
const base = import.meta.env.VITE_API ?? "";
export async function fetchSessionState(session = "default"): Promise<SessionState> {
  const r = await fetch(`${base}/api/session/state?session=${encodeURIComponent(session)}`);
  if (!r.ok) throw new Error(`session state ${r.status}`);
  return r.json() as Promise<SessionState>;
}
export interface LumleyXY { x: number[]; y: number[] }
export interface PhysicsView { case: string; expression: string; n: number; ratio: number | null;
  rans: LumleyXY; dns: LumleyXY; corrected: LumleyXY; geometry: { x: number[]; y: number[]; gain: number[] };
  b12?: { rans: number[]; dns: number[]; corrected: number[] }; error?: string }
export async function fetchPhysicsCases(): Promise<Record<string, string[]>> {
  const r = await fetch(`${base}/api/physics_cases`);
  if (!r.ok) throw new Error(`physics cases ${r.status}`);
  return r.json() as Promise<Record<string, string[]>>;
}
export async function fetchPhysicsView(expression: string, caseId: string): Promise<PhysicsView> {
  const r = await fetch(`${base}/api/physics_view?expression=${encodeURIComponent(expression)}&case=${encodeURIComponent(caseId)}`);
  if (!r.ok) throw new Error(`physics view ${r.status}`);
  return r.json() as Promise<PhysicsView>;
}
export interface SessionInfo { session: string; events: number; modified: number }
export async function fetchSessions(): Promise<SessionInfo[]> {
  const r = await fetch(`${base}/api/sessions`);
  if (!r.ok) throw new Error(`sessions ${r.status}`);
  return r.json() as Promise<SessionInfo[]>;
}
export async function fetchMatrix(session = "default"): Promise<MatrixData> {
  const r = await fetch(`${base}/api/matrix?session=${encodeURIComponent(session)}`);
  if (!r.ok) throw new Error(`matrix ${r.status}`);
  return r.json() as Promise<MatrixData>;
}
// backlog "instant": history arrives at once (live view); "paced": ~20/s animation (Replay).
// skip: events already received (reconnect after the server's idle end).
export function eventsSocket(session = "default", backlog: "instant" | "paced" = "instant", skip = 0): WebSocket {
  const wsBase = base
    ? base.replace(/^http/, "ws")
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  return new WebSocket(`${wsBase}/ws/events?session=${encodeURIComponent(session)}&backlog=${backlog}&skip=${skip}`);
}
export interface RegionsData { image: string | null; source: string; model: string | null; regions: { region: string; box: number[]; max_error?: number; mean_error?: number; severity?: string; source?: string }[]; detail: string }
export interface StartRoundResult { status: string; session?: string; mock?: boolean; round?: number; events?: string; reason?: string }
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

export async function fetchLatex(expr: string): Promise<{ expr: string; latex: string | null; error?: string }> {
  const r = await fetch(`${base}/api/latex?expr=${encodeURIComponent(expr)}`);
  if (!r.ok) throw new Error(`latex ${r.status}`);
  return r.json();
}
export interface ArmSeedRow { seed: number; metric: number | null; expression: string | null; session: string; cost_usd: number; dl?: number | null; no_champion?: boolean }
export interface ArmsFile { file: string; modified: number; mode: string; metric: string; rounds: number; groups: number;
  spent_usd: number; budget_usd: number; incomplete: boolean; dry_run: boolean;
  arms: Record<string, { seeds: ArmSeedRow[]; summary: { mean: number; stdev: number; min: number; max: number } | null }>;
  comparisons?: Record<string, Record<string, number | string | null>> }
export async function fetchArms(): Promise<ArmsFile[]> {
  const r = await fetch(`${base}/api/arms`);
  if (!r.ok) throw new Error(`arms ${r.status}`);
  return r.json();
}
export interface VaultEval { milestone: number; reason: string; mode: string; timestamp: string; scores: any }
export async function fetchVault(): Promise<{ evaluations: VaultEval[]; used: number; max: number }> {
  const r = await fetch(`${base}/api/vault`);
  if (!r.ok) throw new Error(`vault ${r.status}`);
  return r.json();
}
export function artifactUrl(session: string, imagePath: string): string {
  const name = imagePath.split(/[\\/]/).pop() ?? ""; // event paths use Windows separators
  return `${base}/api/artifact?session=${encodeURIComponent(session)}&name=${encodeURIComponent(name)}`;
}

// ---- run control (UI run panel) ----
export interface RunInfo { id: string; kind: "session" | "experiment"; params: Record<string, any>; status: string;
  started: number; ended: number | null; rounds_done: number; round_now: number | null; spent_usd: number;
  sessions: string[]; out_file: string | null; log_file: string | null; message: string }
export interface RunPreset { id: string; label: string; kind: "session" | "experiment"; description: string; params: Record<string, any> }
export interface RunsData { runs: RunInfo[]; presets: RunPreset[];
  limits: { max_rounds: number; max_groups: number; session_dollar_limit: number; usd_per_round_group: number } }
export interface RunStartResult { status: string; reason?: string; needs_archive?: string[]; run?: RunInfo }
export async function fetchRuns(): Promise<RunsData> {
  const r = await fetch(`${base}/api/runs`);
  if (!r.ok) throw new Error(`runs ${r.status}`);
  return r.json();
}
async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path} ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.json() as Promise<T>;
}
export const startSessionRun = (b: Record<string, unknown>) => postJson<RunStartResult>("/api/runs/session", b);
export const startExperimentRun = (b: Record<string, unknown>) => postJson<RunStartResult>("/api/runs/experiment", b);
export const controlRun = (id: string, action: "pause" | "resume" | "stop" | "kill") =>
  postJson<RunStartResult>(`/api/runs/${encodeURIComponent(id)}/${action}`);
