# FlowForge v2

**LLM research agents that propose turbulence-closure corrections for the k-ω SST RANS model, a
deterministic evaluation ladder that scores every proposal, and a live cockpit that shows the whole
process.** Agents write candidate closures in a small, checkable language; constants are fitted by
least squares; every claim is decided by a deterministic score, never by an LLM.

> **Headline (locked test, frozen a priori, one case).** On the held-out 3-D `square_duct`, the
> closure found by **loop v2** cuts SST's anisotropy error by **47 %**
> (error ratio 0.527), ahead of classical sparse regression (0.618), random grammar search (0.658)
> and the original agent loop (0.882). The ranking matches the validation ranking. One locked case,
> frozen a-priori scores (not solved velocity), one champion per approach — see
> [Limits](#limits-read-before-quoting-a-number).

![Mission Control on a loop-v2 session](docs/screenshots/01-mission-control-loop-v2.png)

Methodology authority: [docs/build-spec.md](docs/build-spec.md). Sequencing:
[docs/plans/2026-10-26-flowforge-v2-implementation-plan.md](docs/plans/2026-10-26-flowforge-v2-implementation-plan.md).
Every protocol change and every result, wins and losses, is logged in
[docs/history/decisions.md](docs/history/decisions.md), registered before it was computed.

---

## Contents

1. [What it does](#what-it-does)
2. [Two agent loops](#two-agent-loops)
3. [Results](#results)
4. [What we learned](#what-we-learned)
5. [Follow-up: physics features and 29 hills](#follow-up-physics-features-and-29-hills-exploratory)
6. [Limits](#limits-read-before-quoting-a-number)
7. [The cockpit (screenshots)](#the-cockpit)
8. [Setup and reproduction](#setup-and-reproduction)
9. [Repository layout](#repository-layout)
10. [Guardrails](#guardrails)
11. [Next steps](#next-steps)

---

## What it does

A candidate closure corrects SST's Reynolds-stress anisotropy with Pope's tensor basis:

$$a^{\Delta}_{ij} = g_1(I_1, I_2)\,T^{(1)}_{ij} + g_2(I_1, I_2)\,T^{(2)}_{ij} + g_3(I_1, I_2)\,T^{(3)}_{ij}$$

- **Closure language** (`flowforge/dsl/`): T1..T3 and invariants I1 (strain), I2 (rotation); `+ − ×`,
  guarded `div`/`sqrt`, `exp`, `tanh`, integer powers; at most **25 expression-tree nodes**. T4 and
  I3–I5 are rejected (redundant in 2-D). Invariance and dimensional consistency hold by construction.
- **Targets** (`flowforge/physics/frozen_rans.py`): frozen-RANS correction `a_delta = b_DNS − b_SST` from
  the curated McConkey RANS/DNS dataset (Kaggle, CC-BY-4.0).
- **Fitting** (`flowforge/dsl/expr_fit.py`): least squares on the training flows, realizability-constrained
  (total anisotropy stays inside the Lumley triangle), then constant snapping (0, ±½, ±1, … within 1 %).
- **Score**: error ratio = candidate MSE ÷ SST (zero-correction) MSE on a flow; below 1 beats SST.
- **Selection** (`flowforge/elegance/`): among candidates within 3 % of the best, the shortest
  description length wins (elegance rule, frozen).
- **Red team**: candidates worse than SST on any held-out attack flow are flagged/broken.
- **Locked vault** (`data/locked/`): read only by `scripts/evaluate_locked.py`, at most 3 logged
  evaluations.

### Data splits (data v3, current)

| Split | Flows | Use |
|---|---|---|
| train | periodic hills α 1.0, 1.5; parametric bumps h20, h31, h42; 9 zero-pressure-gradient flat plates | fit constants |
| redteam | converging-diverging channel (Re 12600, 20580); bumps h26, h38 | held-out screen / selection |
| attack hills | periodic hills α 0.5, 0.8, 1.2 | held-out screen / selection |
| validation | curved backward-facing step (`curved_step`) | the reported metric; never seen by an LLM |
| locked | `square_duct` (3-D), `nasa_wall_mounted_hump` | ≤ 3 milestone evaluations |

Data v2 (the decision run) trained on the two hills only; adding the bump and flat-plate families
(already in the downloaded dataset, never ingested before) was the single largest improvement.

## Two agent loops

Both loops share the fitter, scorer, realizability gate, elegance rule, event log and budget meter.
Choose with `scripts/run_arms.py --loop v1|v2` or the **loop v2** toggle in the UI.

**Loop v1 (original, 12 steps, `flowforge/orchestrator/round.py`).** Board → Theorists → Coder → Fitter →
Rung 0 → Rung 1 (halving) → red-team screen → Rung 2 → Rung 3 → Analyst + SAM → Skeptic → Composer →
Champion. Every role is one structured JSON call. Audit finding: Coder, Analyst, Skeptic and Composer
outputs are never read downstream, and in frozen mode rungs 1–3 apply the same metric three times.

**Loop v2 (`flowforge/orchestrator/loop_v2.py`).** Rewired so diagnosis drives proposal and the
proposer sees its results inside the round:

```
 ┌──────── population (top 8, ≤ 2 per tensor set, carried across rounds) ◄──────────┐
 ▼                                                                                   │
Diagnostician (LLM): reads per-flow scores of the population, names the worst flows │
 ▼                                                                                   │
Theorist ×G (LLM): 3 proposals per group from the diagnosis                          │
 ▼                                                                                   │
Fit + score (deterministic): constants on train; per-flow train and held-out ratios ─┤
 ▼                                                                                   │
Reviser (LLM, same group): sees its own per-flow scores, revises once ── re-score ───┘
                                     end of round: Champion (deterministic, same rule)
```

The red team becomes a score column (held-out ratios) instead of a mid-pipeline gate; Coder,
Composer, Skeptic and the LLM red team are not dispatched. **v2.1** adds a 50k-token completion
limit (8k left 11 % of replies empty), the parser's real rejection message (e.g. "Complexity 27
exceeds cap 25"), node counts and the realizable fraction in what the model sees.

## Results

All numbers are **frozen a-priori** error ratios (lower is better, 1.0 = plain SST), 5 seeds,
5 rounds × 2 groups per session, metric `worst_validation_ratio` on `curved_step`.

### Data v3 (current)

| Arm | Mean ± sd | Seeds 42 / 43 / 44 / 45 / 46 | Spend |
|---|---|---|---|
| Sparse regression (no LLM) | **0.748 ± 0.029** | 0.798 / 0.733 / 0.733 / 0.741 / 0.733 | $0 |
| Random grammar search (no LLM) | 0.784 ± 0.055 | 0.753 / 0.730 / 0.781 / 0.874 / 0.781 | $0 |
| Loop v2, swarm | 0.850 ± 0.105 | 0.961 / 0.841 / 0.821 / 0.932 / **0.694** | $6.79 (both v2 arms) |
| Loop v2, no red team | 0.869 ± 0.116 | 0.968 / 0.956 / 0.909 / 0.822 / **0.688** | |
| Loop v2.1, swarm | 0.868 ± 0.046 | 0.818 / 0.887 / 0.826 / 0.929 / 0.881 | $6.86 (both v2.1 arms) |
| Loop v2.1, no red team | 0.871 ± 0.032 | 0.872 / 0.861 / 0.926 / 0.845 / 0.852 | |
| Loop v1, no red team | 0.883 ± 0.043 | 0.868 / 0.852 / 0.955 / 0.890 / 0.851 | $6.43 (both v1 arms) |
| Loop v1, swarm | 0.939 ± 0.035 | 0.964 / 0.879 / 0.939 / 0.959 / 0.957 | |

Loop v2 beats loop v1 (swarm: exact one-sided Mann–Whitney p = 0.075; v2.1 vs v1 p = 0.028) and produced
the best single closures of the project. v2.1 fixed the wiring (no empty replies, usable candidates in
later rounds) and cut the seed-to-seed spread from 0.105 to 0.046, but not the mean. On seed averages no
LLM loop beats sparse regression or random search on this metric.

### Locked milestone 1 (`square_duct`, one evaluation for a pre-registered set)

Per approach, the champion with the best validation ratio in the completed data-v3 runs, as trained
and refit on all non-locked data. Set fixed in `decisions.md` before the vault was opened.

| Candidate | Validation | **Locked** | Locked, refit on all data |
|---|---|---|---|
| **Loop v2** `0.26·T1 + (−7.5 + 7.4·tanh(12.5·I1))·T2 + 3.9·exp(−1.5·I1)·T3` | 0.688 | **0.527** | **0.520** |
| Constant model (data v2, post hoc) `0.333·T1 − 3.05·T2 + 1.5·T3` | 0.761 | 0.610 | — |
| Sparse regression | 0.733 | 0.618 | 0.619 |
| Random grammar | 0.730 | 0.658 | 0.607 |
| Loop v1 | 0.851 | 0.882 | 0.754 |
| Constant form refit on all data | — | — | 0.957 |

### Data v2 (decision run and follow-ups, pre-registered)

| Arm | Mean ± sd |
|---|---|
| Swarm (decision run) | 0.845 ± 0.018 |
| Swarm, no red team (decision run) | 0.858 ± 0.011 |
| Sparse regression (decision run) | 0.823 ± 0.004 |
| Replication (seeds 47–51): swarm / no red team / sparse | 0.888 ± 0.064 / 0.833 ± 0.071 / 0.828 ± 0.007 |
| Single-LLM control · random grammar · sparse + red team | 0.832 · 0.837 · ≈ 0.819 |
| Swarm + SAM + red-team ratio 1.10 | 0.820 ± 0.034 |

RP1 (red team improves generalization) and RP2 (LLM beats sparse regression) were **not supported**
on data v2 (RP1 p = 0.155, not replicated; RP2 p = 0.996).

## What we learned

1. **The proposer was not the bottleneck; the data was.** On data v2, swarm ≈ single LLM ≈ random
   grammar. With two near-identical training hills, every flow available for fitting or selection
   agreed, and none predicted the validation step. Adding the bump and flat-plate families moved
   sparse regression from 0.823 to 0.748 at zero API cost.
2. **The best coefficients differ by flow family.** Fitted constants for T2 range from −5.2 (flat plate)
   through −3.1 (hills) to −0.3 (tall bump). A coefficient that depends on strain (I1) can carry that
   difference; the loop-v2 champion does exactly that, and it transferred to the 3-D duct.
3. **Orchestration topology matters, wiring defects matter more.** Moving diagnosis before proposal and
   letting the proposer see per-flow results inside the round beat the original pipeline. In loop v2,
   later rounds were mostly wasted on over-cap expressions (121), non-realizable fits (147) and empty
   replies (30/262) until v2.1 fixed the feedback.
4. **Held-out flows from the same families do not predict an unseen geometry.** Selecting on them
   (opt-in `--selection heldout`) changed 1 seed in 5; the agents improve steadily on everything they
   can see, and only part of that reaches `curved_step`.
5. **The red-team screen at ratio 1.0 is too strict** on data v3: the no-red-team arm scored better in
   loop v1.

## Follow-up: physics features and 29 hills (exploratory)

Run after the decision and data-v3 runs, on branches `explore/medium-formulas` and `explore/llm-features`.
Everything is **frozen a priori and exploratory**, registered in
[decisions.md](docs/history/decisions.md) before it ran; no locked data was touched. It does not change
the results above.

### 1. What limits short formulas (no API)

On `curved_step`, with the same inputs the agents get (I1, I2, T1..T3):

| Model | Error ratio |
|---|---|
| Best agent closure (loop v2) | 0.688 |
| Deterministic greedy search, ≤ 25 / 36 / 100–450 nodes | 0.685 / 0.646 / 0.61–0.64 |
| Non-parametric g(I1, I2) learned from train (k-nearest neighbours), realizability enforced | ≈ 0.48 |
| Point-by-point projection on T1..T3 (fitted on validation itself: a bound, not a model) | 0.0003 |

The tensor basis is not the limit, and there is headroom (0.69 → ≈ 0.48), but only for a g(I1, I2) that
varies sharply, a lookup table rather than a readable formula. Short formulas plateau around 0.63–0.65,
and a plain greedy search already reaches what the agents find. Scripts: `scripts/ceiling*.py`,
`scripts/medium_formulas.py`; loop v2.1 with a 60-node cap (E6, `scripts/run_e6.py`) is in decisions.md.

### 2. Loop v3: the LLM proposes physics, a deterministic search writes the formula

```
Physicist (LLM): proposes 1–3 dimensionless flow features + a physical rationale, drops useless ones
 ▼   (sees: active features and how much each helps on held-out flows, best formula, rejected features)
Feature check (deterministic): whitelisted primitives (k, ω, ν_t, wall distance, ∇p, P_k, …);
 ▼   dimensionless test = value unchanged when velocities ×2 and lengths ×3; finite; not constant
Greedy search (deterministic): best formula sum_k g_k(I1, I2, features)·T_k within 40 nodes, fit on train
 ▼
Held-out gain of each feature (search re-run without it) → back to the Physicist
```

Code: `flowforge/orchestrator/loop_v3.py`, `flowforge/data/feature_dsl.py`, `flowforge/search/omp.py`,
role `physicist` (`prompts/physicist.yaml`). Controls use the same search with fixed inputs: I1, I2 only
(**invariants**), or I1, I2 plus 10 textbook features after Ling & Templeton (2015) and Wang et al. (2017)
(**standard**). All 75 features the LLM proposed in the first 5-round run passed the unit check; P_k/ε
(non-equilibrium) was proposed independently in every seed. A session costs about $0.15–0.50.

### 3. A fairer validation: 29 parameterized periodic hills

[Xiao et al. (2020)](https://tmbwg.github.io/turbmodels/Other_DNS_Data/parameterized_periodic_hills.html)
provide 29 DNS at Re_H 5600 (slopes α 0.5–1.5, three lengths, three heights) but no RANS baseline, so it is
computed here (`flowforge/data/hills29.py`, `scripts/run_hills29.py`): terrain-following mesh from the DNS
wall, OpenFOAM k-ω SST, DNS interpolated to the RANS cells, same arrays and conventions as the McConkey
ingest. Check on the classic hill against McConkey's: separation x = 0.98–7.67 vs 0.96–7.59, sparse
champion ratio 0.674 vs 0.673. Split fixed before any score: 11 validation hills (a Latin square over
slope × length × height, plus α 0.75 and 1.25), 18 training hills. Data v4 is opt-in:
`FLOWFORGE_CASES=configs/cases_v4.yaml`.

### Results (≤ 40 nodes, 5 seeds; lower is better)

| Arm | Trained on | `curved_step` | **11 validation hills, mean** |
|---|---|---|---|
| Invariants (no LLM) | data v3 | 0.728 | 0.572 |
| Standard features (no LLM) | data v3 | **0.670** | 0.572 |
| Loop v3, 5 rounds | data v3 | 0.705 ± 0.012 | 0.574 ± 0.008 |
| Loop v3, 15 rounds | data v3 | 0.704 ± 0.015 | 0.560 ± 0.022 |
| Loop v3, 15 rounds, seeded with the standard features | data v3 | 0.692 ± 0.009 | 0.555 ± 0.026 |
| Invariants (no LLM) | data v4 (+ 18 hills) | 0.767 | 0.571 (worst 0.635) |
| Standard features (no LLM) | data v4 | 0.771 | 0.529 (worst 0.580) |
| **Loop v3, 5 rounds** | data v4 | 0.746 ± 0.042 | **0.504 ± 0.036** (0.457–0.556) |
| Loop v3, 5 rounds, seeded | data v4 | 0.751 ± 0.029 | 0.499 ± 0.037 |

API spend for all loop-v3 runs: about $7.3.

### Key messages

1. **One validation flow was misleading.** Across the 15 loop-v3 sessions trained on data v3, the
   `curved_step` score is uncorrelated with the 11 hills (Spearman −0.03), while the held-out selection
   flows predict them (0.59, p = 0.02). The textbook features' advantage on `curved_step` disappears on
   the hills.
2. **Inventing formulas, the LLM did not beat classical search; proposing physics, it shows an edge.**
   Trained with the hills, the LLM's features beat the textbook set on the 11 validation hills in
   4 of 5 seeds (−5 % on average, best seed −14 %) and beat I1, I2 alone in 5 of 5 (−12 %).
   **Not yet significant**: one-sided sign test p = 0.19, seed spread (± 0.036) as large as the gap.
3. **More agent time did not help; a better judge does.** 15 rounds scored the same as 5 on `curved_step`
   (0.704 vs 0.705). What changed the picture was measuring on 11 flows instead of one.
4. **Trade-off:** training on the hills makes every arm worse on `curved_step` (≈ 0.75–0.77): the
   corrections follow the family that dominates the training points.

Follow-up limits: exploratory, after the decision run; the hills' SST baselines are ours (one mesh and
solver setup, validated on one geometry); realizability is reported, not enforced, in loop v3; 1500 points
per case on data v4 (memory); controls are single deterministic runs, compared with 5 LLM seeds.

## Limits (read before quoting a number)

- **Frozen a priori, not solved flow.** The solver oracle gate (`tests/integration/test_solver_oracle.py`)
  is still red: injecting the exact DNS-derived correction moves velocity *away* from DNS (ratio
  1.06–1.08 vs the frozen gate 0.70). Every number here is labelled `frozen`.
- **One validation flow, one locked flow.** `curved_step` is the only step-like flow; only
  `square_duct` is ingested in the vault on this machine. The follow-up adds 11 validation hills and shows
  that `curved_step` alone does not rank models the way the hills do.
- **The locked comparison is one champion per approach**, chosen by best validation seed (same rule for
  every approach). On seed averages loop v2 does not beat sparse regression.
- **Post-hoc items are labelled.** The constant model's form was found after looking at validation.
- **Data v3 results are not pooled with data v2** (different protocol).

## The cockpit

React + Plotly UI over a FastAPI backend; everything streams from `runs/<session>/events.jsonl`.
Open a page and session directly with `http://localhost:5173/?view=Results&session=arms-swarm-v2-s46`.

| | |
|---|---|
| ![Loop v1](docs/screenshots/02-mission-control-loop-v1.png) **Mission Control, loop v1**: 12-node agent graph, candidate funnel, progress vs SST, red-team arena, Analyst + SAM error regions | ![Generalization matrix](docs/screenshots/03-generalization-matrix.png) **Generalization Matrix**: candidates × flows, train / attack / validation |
| ![Candidate inspector](docs/screenshots/04-candidate-inspector.png) **Candidate Inspector**: equation, per-flow ratios, lineage | ![Physics view](docs/screenshots/05-physics-view.png) **Physics View**: fields and corrections on the flow |
| ![Results](docs/screenshots/06-results.png) **Results**: arms table, every session, accuracy vs simplicity | ![Locked vault](docs/screenshots/07-locked-vault.png) **Locked Vault**: milestone scores from the access log |
| ![Replay](docs/screenshots/08-replay.png) **Replay**: scrub through a recorded session at zero cost | |

**Run control** (Mission Control): presets from a free smoke test to the full experiment, session runs
or the 3-arm experiment, loop v1/v2 toggle, red team, SAM 3.1, budget cap; pause / resume / stop between
rounds. Live runs ask for confirmation with a cost estimate and cannot exceed `session_dollar_limit`.

## Setup and reproduction

Prerequisites: Python 3.12, Node 18+, a Meta Model API key for live runs. Docker Desktop only for the
solver gates. Run everything from the repository root.

```bash
pip install -e ".[dev]"
cd ui && npm install && cd ..
cp .env.example .env            # put MODEL_API_KEY in .env (git-ignored); FLOWFORGE_REPLAY=1 = zero-token replay
```

**Data.** Put `komegasst.csv` and `REF.csv` from the
[curated Kaggle dataset](https://www.kaggle.com/datasets/ryleymcconkey/turbulence-modelling-using-machine-learning)
in `data/raw/` (SHA-256 in `data/raw/manifest.json`), then:

```bash
python -m flowforge.data.ingest_csv                  # every case in configs/cases.yaml, incl. data-v3 bumps and flat plates (slow: rescans the CSVs per case)
python -m flowforge.data.ingest_csv --attack-cases   # the attack hills (alpha 0.5, 0.8, 1.2)
# no Kaggle access: python scripts/download_data.py --synthetic-fallback (smoke data only, never results)
```

**Tests.**

```bash
python -m pytest tests/unit tests/agents tests/science -q     # offline, no Docker, no key (347 tests)
cd ui && npx tsc --noEmit && cd ..
python -m pytest tests/integration -q                          # solver gates: Docker + flowforge-openfoam image
```

**Experiments** (frozen mode; `--budget-usd` is a hard cap):

```bash
# 3 arms (swarm, no red team, sparse), 5 seeds, original loop / loop v2
python scripts/run_arms.py --rounds 5 --groups 2 --seeds 42,43,44,45,46 --budget-usd 12
python scripts/run_arms.py --rounds 5 --groups 2 --seeds 42,43,44,45,46 --budget-usd 12 --loop v2
# same per seed, so seeds run in parallel (used for E3-E5): SEED TAG LOOP BUDGET
python scripts/run_arms_seed.py 42 e4-v2 v2 2.4
# no-LLM controls ($0): random grammar, constant model
python scripts/run_controls.py --control random_grammar --stub-redteam --out runs/arms/e2-v3-random.json
python scripts/run_controls.py --control constant --out runs/arms/e2-v3-constant.json
# combined data-v3 table and the locked milestone set
python scripts/summarize_data_v3.py
python scripts/build_milestone_set.py
python scripts/evaluate_locked.py --milestone 1 --candidates-file runs/arms/milestone1-candidates.json --reason "..."
```

**Follow-up** (loop v3 and the 29 hills; Docker Desktop and the `flowforge-openfoam:local` image for the
hills):

```bash
python scripts/featurize_cases.py                   # standard features + primitives -> data/features/ (data-v3 cases)
# unzip dns-29-periodic-hills.zip (NASA TMR, 1.2 GB) first; ~25 min with 6 parallel SST solves
python scripts/run_hills29.py path/to/DNS_29_Periodic_Hills
python scripts/control2_features.py                 # controls, data v3 ($0)
python scripts/run_loop_v3.py --tag v3 --seeds 42 --rounds 5                       # add --seed-standard --max-features 16 for the seeded arm
python scripts/eval_hills29_a.py                    # data-v3 arms scored on the 11 validation hills ($0)
FLOWFORGE_CASES=configs/cases_v4.yaml python scripts/run_loop_v3.py --tag v4 --seeds 42 --rounds 5 --train-points 1500
python scripts/ceiling.py && python scripts/medium_formulas.py                     # headroom probes ($0)
```

**Cockpit.**

```bash
python -m uvicorn flowforge.api.server:app --host 127.0.0.1 --port 8000
cd ui && VITE_API=http://localhost:8000 npx vite build && cd ..
python -m http.server 5173 --bind 127.0.0.1 --directory ui/dist    # open http://localhost:5173
```

(Or `cd ui && npm run dev`; the Vite proxy forwards `/api` and `/ws`.) Observed costs: about $0.15 per
live round with 2 groups; 5 seeds × 2 swarm arms ≈ $6–7. Mock runs, dry runs and replay cost nothing.

## Repository layout

```text
flowforge/
  agents/        role dispatcher, prompt loader, Pydantic schemas, model runtime (budget, replay)
  orchestrator/  round.py (loop v1), loop_v2.py, loop_v3.py (features), history.py (session feedback)
  dsl/           closure grammar, parser (25-node cap), evaluator, constant fitter
  search/        omp.py: deterministic greedy formula search used by loop v3 and its controls
  physics/       invariants, tensor basis, realizability, frozen-RANS targets
  data/          CSV ingest, Zarr stores, split guard (locked isolation), frozen-field loading,
                 features.py + feature_dsl.py (loop-v3 features), hills29.py (29-hill SST baselines)
  ladder/        rungs, halving, realizability gate
  elegance/      description length, snapping, champion rule
  baselines/     sparse regression baseline
  redteam/ composer/ literature/ render/ (SAM 3.1 client) solver/ (OpenFOAM runner) api/
openfoam/        correctedKOmegaSST C++ class, case templates, hill meshing
configs/         cases.yaml (splits), budgets.yaml (roles, $ limit), tolerances.yaml (frozen)
prompts/         versioned role prompts (hash logged on every call)
library/         cross-session memory: modules, attacks, rejected, findings, literature cards
scripts/         run_arms, run_arms_seed, run_controls, evaluate_locked, build_milestone_set, summarize_data_v3
tests/           unit, agents, science (offline); integration (Docker solver gates)
ui/              React + Plotly cockpit (Vite)
docs/            build-spec, plans, history/decisions.md (every protocol change and result), screenshots
data/ runs/ scratch/   git-ignored: datasets + locked vault, session outputs, probes
```

## Guardrails

- `data/locked/` is read only by `scripts/evaluate_locked.py`; every access is logged in
  `runs/vault_access.log`, at most 3 evaluations, expressions validated before the vault opens.
- Tolerances in `configs/tolerances.yaml` and the 25-node cap are frozen; never loosened to pass a check.
- No LLM sees validation or locked scores (unit-tested for loop v2); agents never score themselves.
- Every result is labelled `frozen`, `short` or `full`; mock and synthetic runs are bookkeeping only.
- Protocol changes are registered in `docs/history/decisions.md` before the numbers they produce.
- `.env`, `data/`, `runs/`, `scratch/` and `ui/node_modules/` are git-ignored.

## Next steps

1. **More validation flows, then more seeds.** The 11 hills settled the `curved_step` question; the
   loop-v3 edge over textbook features (4/5 seeds) needs more seeds or a second family of validation
   flows to become significant, ideally a second step-like flow.
2. **k-corrective frozen RANS** (SpaRTA's k-equation residual R as a real k source, implicit injection
   of the linear part) so the solver oracle passes and frozen scores can be checked as solved velocity.
3. **Loop v2 follow-ups**: per-family residuals for the Diagnostician, leave-one-family-out scoring in
   the population, a looser red-team ratio.
