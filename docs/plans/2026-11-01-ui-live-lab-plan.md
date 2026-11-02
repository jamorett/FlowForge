# FlowForge UI — "Live Lab" implementation plan (2026-11-01)

**Status (2026-11-01, implemented):** steps 0–7 done. Step 3 extends Steven's Physics view
(Lumley triangle + gain map) with b12 station profiles instead of a new `/api/compare`;
`/api/physics_view` now returns `b12`. SAM panel uses analyst-event regions + `/api/artifact`.
Results reads `/api/arms`. Step 2 clusters view done (ClusterView: tensor set x coefficient family).

Goal: a demo-grade cockpit where you *watch* the science happen: agents as an
animated node graph, candidates flowing through the ladder, the red team
attacking, proposed equations compared against DNS ("reality"), and SAM 3.1
showing where each candidate fails. Read-only; every number traceable to an
event. All accuracy shown is a priori and labelled `frozen`.

Deadline context: submit Nov 4 ~15:00 ET. Cut order at the bottom.

## What already exists (reuse, do not rebuild)

| Piece | Where | Use |
|---|---|---|
| Live event stream with reconnect + `skip` | `GET /ws/events?session=&skip=`, `ui/src/components/EventFeed.tsx` | Single source of truth for all animation |
| Event fields per step | `runs/<session>/events.jsonl` | board: `mechanisms`, `budget_split`; theorist: `expressions`, `group`, `mechanism`; fit: `fits[]` (`original`→`expression`, `mse_before/after`); rung0-3: `survivors[]` (`expression`, `score`); analyst: `failure_regions`; skeptic: `objections`; redteam: `attacks[]` (`case_id`, `flow`); champion: `champion` (`expression`, `dl`, `train`, `validation{case: ratio}`, `attack_ratios`, `worst_validation_ratio`) |
| Matrix (candidates × flows) | `GET /api/matrix` | Comparison heatmap |
| SAM regions | `GET /api/latest_regions` (+ `err_r{round}_{i}.png` in session dir) | Error-map overlay |
| Equation rendering | `EquationView.tsx` (KaTeX) | Equations everywhere |
| Plotly | `plotly.js-dist-min` (installed) | All charts |
| Session state, polling | `GET /api/session/state`, TanStack Query `refetchInterval` | Status chips |

No new npm dependency is required (SVG + CSS transitions + Plotly). If force
layout is wanted later, `d3-force` would need the security audit first.

## Step 0 — Event store (foundation, ~1.5 h)

`ui/src/state/events.ts`: one React context fed by the existing socket logic
(move it out of EventFeed). Normalizes each event to
`{ i, round, group, role, kind, t, payload }` and derives:
- `candidates`: map expression → `{ proposedBy, round, group, stage: proposed|fit|rung0..3|rejected|champion, scores, rejectedReason }` (rejected = in rung N but not N+1; rung3 drop = `non_realizable`)
- `champions[]` per round, `attacks[]`, `objections[]`, `regions` per round.
- `cursor` for replay scrubbing (same store drives Replay page).

Accept: unit-free check — feeding `runs/verify-906/events.jsonl` yields 3
champions, attacks on 3 hills, every candidate with a terminal stage.

## Step 1 — Agent graph with animated interactions (~3 h) — demo moment 1

`components/AgentGraph.tsx` (SVG, fixed ring layout, no physics):
- Nodes: Board (center-top), Theorist g0/g1, Coder/Fitter, Ladder (R0→R3 as a
  4-node chain), Analyst, Skeptic, Red Team (accent colour), Composer, Champion.
- Edges follow the round order. On each event: pulse the emitting node,
  animate a dot along the edge to the next role (CSS `offset-path`, 600 ms),
  edge label shows payload count ("3 candidates", "1 survivor").
- Node badge = last action (mechanism, # objections, # attacks).
- Rejections animate as a dot falling off the ladder with reason tooltip.
- Click a node → side drawer with its raw events (reuse EventFeed rows).

Accept: watching a live round, every role lights up in order; dot counts
equal `len(expressions)` / `len(survivors)` in the log.

## Step 2 — Candidate funnel / clusters (~2 h)

`components/CandidateFunnel.tsx`: Plotly scatter, x = ladder stage, y = a
priori MSE (log), one marker per candidate, colour = group, shape = round;
lines connect proposal → fitted version (shows the fitter moving constants).
Rejected markers greyed with reason; champion starred. Second view:
"clusters" = candidates grouped by tensor signature (T1/T2/T3 present) as
bubbles sized by count, coloured by best ratio.

Accept: counts per stage match rung events; the realizability-rejected
candidates are visible as greyed markers at rung 3.

## Step 3 — Equations vs reality (~3.5 h) — demo moment 1, the core comparison

Backend: `GET /api/compare?session=&expression=&case=` in `api/server.py`
(read-only; allowed cases = train + validation + attack from
`frozen_fields`; **never locked** — route through `guard_swarm_path`).
Returns a deterministic subsample (≤4000 pts, seed 0) of
`x, y, b_dns_ij, b_sst_ij, b_pred_ij` (b_pred = b_sst + candidate a_delta)
for ij in {11, 12, 22}, plus per-case `ratio`. Cache by (expr, case).
Test: shapes, symmetry/trace-free of b_pred, locked case → 403.

UI `pages/RealityCheck.tsx`:
- Spatial maps (Plotly heatmap/scatter on x,y): DNS vs SST vs candidate for
  b12 (shear anisotropy), and |error| maps candidate vs SST side by side.
- Profiles at hill stations x/h = 0.5, 2, 4, 6 (nearest points binned in y):
  DNS line, SST line, candidate line — the "law vs reality" picture.
- Barycentric map: predicted vs DNS stress states (realizability triangle).
- Header: equation (KaTeX), DL bits, worst validation ratio, label `frozen`.

Accept: for the 0.78 champion on curved_step the endpoint ratio equals the
logged `validation.curved_step.ratio` to 1e-9.

## Step 4 — Red team arena (~2 h) — demo moment 2

`components/RedTeamArena.tsx`: one card per attack hill (alpha 0.5/0.8/1.2)
with the hill silhouette (from store coordinates via `/api/compare` x,y
envelope), intended failure mode text, and per-champion ratio bars
(`attack_ratios`) vs SST = 1.0 line; broken (ratio ≥ 1) flashes red with the
attack report. Timeline strip: attacks per round, breaks per round.
Arm toggle: swarm vs no-red-team sessions side by side (RP1 view).

Accept: bars equal logged `attack_ratios`; no-red-team sessions show "no
attacks" explicitly rather than empty space.

## Step 5 — SAM panel (~2 h)

Extend CandidateInspector: show the round's analyst error-map PNG
(`err_r{round}_{i}.png`, served via a small static route
`GET /api/artifact?session=&name=` restricted to `[A-Za-z0-9_.-]+\.png` in that
session dir) with SAM regions overlaid (boxes/masks from
`/api/latest_regions`), each region labelled and linked to the analyst's
`failure_regions` text and the next hypothesis. Badge per result:
`sam-3.1` / `local-fallback` / `none` (never misreported). SAM calls cost API
credits: default `use_api=false`, explicit button to run live.

Accept: region count and labels equal the endpoint; badge matches `source`.

## Step 6 — Comparison dashboard (~2 h) — demo moment 3

`pages/Results.tsx` reading `runs/arms/final-*.json` via
`GET /api/arms/latest`: arm table (mean ± std, all 3 sessions, wins and
losses), strip plot of per-session worst validation ratio per arm with SST =
1.0 line, sparse baseline equations shown next to the swarm champion (simplicity
contrast), and the Elegance plot (worst error vs DL, champion marked, 3%
band shaded). Locked columns grey until a milestone is logged.

Accept: numbers equal the JSON; `frozen` label on every chart.

## Step 7 — Layout, motion polish, replay (~2 h)

Mission Control becomes a 3-pane lab: AgentGraph (left, large), live
CandidateFunnel + champion card (right), EventFeed (bottom, collapsible).
Replay page reuses the event store with a scrubber and 1×/4×/16× speed
(FLOWFORGE_REPLAY=1 for zero tokens). Respect `prefers-reduced-motion`.

## Order and time (≈18 h of work)

| Day | Steps |
|---|---|
| Nov 2 | 0, 1, 3 (graph + reality check = the core demo) |
| Nov 3 | 4, 6, 2 |
| Nov 4 AM | 5, 7, record video from Replay |

Cut order if slipping: 2 clusters view → 5 SAM overlay → replay speeds.
Never cut: Step 3 labels/`frozen`, locked-data exclusion in `/api/compare`.

## Verification per step

`npx tsc --noEmit` and `npx vite build` (exit 0); backend `pytest tests/unit`
for new endpoints; manual check against a real session (`verify-906`,
`arms-swarm-s42`). Serve the built UI statically
(`python -m http.server 5173 --bind 127.0.0.1 --directory ui/dist`) — the
Vite dev server has open advisories (esbuild/vite) fixed only in vite 8.
