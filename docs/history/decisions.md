# Decisions log

## 2026-11-01 — `converging_diverging_channel` moves from `validation` to `redteam`

**Why:** the frozen red team (rung-1 screen) probed attack hills *plus* every validation case, and
excluded any candidate worse than SST there. Validation is also where the RP1 metric
(`worst_validation_ratio`) is scored, so the swarm arm was filtered on its own evaluation set. The
live probe of 2026-11-01 confirmed it: all 3 frozen breaks came from `converging_diverging_channel`
(validation), none from the attack hills.

**Change:** new split `redteam`, used only by the red-team probe set; `converging_diverging_channel`
moves there. Validation keeps `curved_step`. The probe set is attack hills + `redteam` cases, never
train or validation cases. Locked cases (`square_duct`, `nasa_wall_mounted_hump`) are unchanged and
remain the independent check.

**Not changed:** `REDTEAM_BREAK_RATIO` (1.0) and `configs/tolerances.yaml`.

**Consequence:** results produced before this change (red-team screen + validation ratio) are not
comparable to later ones; the 3×5 frozen pilot runs only after it.

## 2026-11-01 — I3, I4, I5 rejected by the DSL and removed from the sparse library

**Why:** measured on the frozen train/validation/red-team stores (4000 points each): I3 and I4 have
rms ~1e-5 (numerical noise; I1, I2 ~0.04) and I5 == 0.5·I1·I2 to relative residual 1e-16. In 2-D
flows they carry no independent information (Pope 1975), the same situation as T4, which was
already rejected. Expressions using them fit noise and can blow up off-training (e.g. div(1, I3)).

**Change:** the parser rejects I3/I4/I5 with an explicit reason; the Theorist prompt (v10) lists
only I1, I2; the sparse baseline library drops I3/I4/I5 so both arms share the same symbol set
(RP2 fairness). The sparse collinearity threshold (0.999) is unchanged.

## 2026-11-01 — Considered and rejected: Jacobian collinearity filter on the swarm's fitted constants

Tried rejecting fits whose constant-Jacobian columns have |corr| > 0.999 (the sparse baseline's
threshold). On real train data it rejected the best known candidate
`(a * div(1, b + I1)) * T1 + c * T2 + d * T3` (validation ratio 0.622): a and b trade off where I1
is small, which is ordinary nonlinear-fit conditioning, not the failure it targets. The targeted
failure (huge opposite coefficients, e.g. `a*I1*T1 + b*tanh(I1)*T1`) is already caught by the
constant bound C_MAX = 1e3 (verified: "constant at bound"). Not adopted.

## 2026-11-01 — Arm comparisons report exact one-sided p-values

`scripts/run_arms.py` output gains `comparisons` (RP1 swarm vs swarm_no_redteam, RP2 swarm vs
sparse_baseline): Mann–Whitney U, exact permutation p (one-sided, lower worst_validation_ratio
better) and p_min. With 3 seeds per arm p_min = 1/20 = 0.05, so no 3-seed comparison can reach
p < 0.05; results are reported as effect + spread, not as significance claims.

## 2026-11-01 — Theorist v11 (structural diversity) and reasoning: high for Theorist and Skeptic

**Why:** frozen pilot 1 (3 arms × 3 seeds × 5 rounds, $2.96, `runs/arms/pilot-2026-11-01.json`):
all 179 Theorist proposals used saturating coefficients (tanh/div/exp); none was polynomial, and
seeds converged to the same champion. The prompt's examples anchored the form. The Theorist, the
key creative role, also ran without a reasoning setting while the Board had `reasoning: high`.
(`max_tokens` in budgets.yaml is not used by the dispatcher, which sends 8192.)

**Change:** `prompts/theorist.yaml` v11: exactly 3 candidates per call, from 3 different coefficient
families (polynomial, saturating/rational, mixed), at least one outside the previous best forms;
polynomial examples added. `configs/budgets.yaml`: `reasoning: high` for theorist and skeptic.
Same model (`muse-spark-1.3-contributor`) and same settings for both swarm arms.

**Probe (1 round, not a result):** 2 of 6 proposals polynomial; the polynomial `-39.5·I1·T2` forms
were broken by the red team on converging_diverging_channel (ratio 1.10–1.19), the same failure as
the sparse baseline (1.05–1.10).

**Consequence:** pilot 1 is superseded; pilot 2 reruns the same protocol with v11.

## 2026-11-01 — Realizability filter before the rung-2 halving

**Why:** frozen pilot 2 (`runs/arms/pilot2-2026-11-01.json`, $3.09): 23 of 30 swarm rounds ended
`all_rejected` (pilot 1: 10 of 30) and 3 of 6 swarm seeds had no champion, so RP1/RP2 were not
computable. The rung-2 halving kept one candidate per round; rung 3 then rejected it as
non-realizable (it left the barycentric triangle at 14–138 of 8000 train points), although
realizable candidates were in the rung-1 pool. Offline check: every round champion that did pass,
and the sparse baseline, are realizable on train data, so the gate itself is fair.

**Change:** `flowforge/ladder/ladder.py` `realizable_only` applies the same realizability check
(total anisotropy `b_rans + pred`) to the rung-1 survivors before `rung2_short`; rung 3 still
re-checks. The rung-2 event logs the dropped expressions as `non_realizable`, and session history
reports them to the Theorist like rung-3 rejections. The gate and its tolerance are unchanged; only
its position moves ahead of the halving. Complements the realizability-constrained constant fit
(commit cb9655a).

## 2026-11-01 — A seed without a champion scores 1.0 (no correction)

**Rule (fixed before pilot 3):** a swarm seed that ran every planned round without an errored round
but never produced a champion delivers no correction, so it scores `worst_validation_ratio = 1.0`
(plain SST) and counts in RP1/RP2 like any other seed. Same rule for every arm (the sparse baseline
always produces a model). A seed cut by the budget or by an errored round stays missing and the arm
is reported incomplete. Each seed row carries `no_champion`; the count per arm is reported
separately as a descriptive.

**Why not drop such seeds:** dropping them favors the arm that fails more often (only its
successes are compared), and with 3 seeds per arm a dropped seed leaves a comparison that cannot
reach any useful p (1 vs 3 seeds: p_min = 0.25). The extra spread from a 1.0 is real variability
of the method, not noise to hide.

## 2026-11-02 — Decision run: 5 seeds per arm, metric unchanged

**Fixed before running:** the decision run (S7.1) is `scripts/run_arms.py --rounds 5 --groups 2
--seeds 42,43,44,45,46 --budget-usd 12`, frozen mode, output `runs/arms/decision-2026-11-02.json`.
Pilots 1–3 tuned the protocol and are not results.

- **Seeds:** 5 per arm (spec: at least 3). With 3 vs 3 the smallest exact one-sided p is 0.05, so
  no comparison could reach p < 0.05; with 5 vs 5 it is 1/252 ≈ 0.004. Cost ≈ $5.5 at pilot-3
  rates. `run_arms.py` now accepts ≥ 3 distinct seeds and summarizes an arm only when every seed
  has a metric.
- **Metric:** unchanged, `worst_validation_ratio` over the validation split (`curved_step`), for
  RP1 and RP2. The red-team split (`converging_diverging_channel`) stays out of the metric; any
  number on it is reported as a post-hoc descriptive, never as an RP result.
- **No-champion rule:** a champion-less seed scores 1.0 (entry of 2026-11-01).
- **Pilot-3 reference (not a result):** swarm 0.852 ± 0.032, no red team 0.842 ± 0.021, sparse
  0.821 ± 0.003; RP1 p = 0.65, RP2 p = 0.80 (3 seeds).

**Code version of the decision run:** commit `7e0ed5f` plus the uncommitted 5-seed change to
`scripts/run_arms.py` described above. Later commits (Live Lab UI, run control, Analyst v3 with
segmented error regions, 2026-11-01 evening, merged after the run) change the Analyst's inputs; a
rerun on newer code is a different protocol and is not pooled with this run.

**Result (frozen, 5 seeds, $5.88, `runs/arms/decision-2026-11-02.json`):** swarm 0.845 ± 0.018,
swarm_no_redteam 0.858 ± 0.011, sparse_baseline 0.823 ± 0.004. RP1 U = 18/25, exact one-sided
p = 0.155 (not significant; direction favors the red team). RP2 U = 1/25, p = 0.996 (sparse better
on the registered metric). All 10 swarm seeds produced a champion (no 1.0 imputation).

## 2026-11-02 — Exploratory follow-ups to the decision run (declared before running)

All of these are **exploratory**: none changes the decision-run result above, none touches
`data/locked/`, and each is reported separately with its own label. No swarm algorithm change
(feature freeze 2026-11-01); new code is analysis scripts and baselines only.

- **B1 Replication (RP1/RP2, independent):** the decision-run command with seeds 47,48,49,50,51,
  run in a separate worktree pinned to commit `6f310f4` (= decision-run code), output
  `runs/arms/replication-2026-11-02.json`. Primary: the replication's own RP1/RP2 exact p-values.
  Secondary, descriptive only: the 10-seed pooled table (decision + replication).
- **B2 Single-LLM control:** the same Theorist prompt, model and settings proposes candidates with
  no Board, Analyst, Skeptic or Composer and no session history; same fitter, ladder,
  realizability gate, red-team screen and champion selection; 5 seeds × 5 rounds. Asks whether
  the role structure adds anything beyond one LLM plus the ladder. Compared descriptively.
- **A2 Sparse + red team:** the sparse baseline's alpha path (one model per alpha) passes the same
  red-team screen (worse than SST on any redteam/attack case = excluded); the best surviving model
  by train ratio is that seed's champion. Tests the spec's fallback "the red team may still help
  classical search".
- **A3 Random grammar search:** no LLM; random expressions from the same grammar (I1, I2,
  T1..T3, tanh/div/exp, linear-use rule), the same number of proposals per seed as the swarm
  (6 per round × 5 rounds), same fitter, ladder and selection. Tests whether the LLM beats
  undirected search.
- **A1, A4, A5 (analysis only):** realizability of every champion on every non-train, non-locked
  case; RP5 ranking of attack cases by how many candidates each breaks; structural diversity per arm.
- **C A posteriori (full solver):** each of the 15 decision-run champions and SST alone on the
  periodic hill (data-derived mesh, `correctedKOmegaSST`, correction computed once from the SST
  solution and held fixed). Metric: normalized RMS error of U vs DNS, as in the oracle gate. No
  candidate is selected: all 15 are run. Labelled `full`, separately from the `frozen` results.

**Update (same day) — C cancelled:** the solver oracle gate was re-run with Docker up
(`pytest tests/integration/test_solver_oracle.py tests/integration/test_solver_identity.py`,
exit 1: identity 2 passed, oracle 1 failed). Injecting the DNS-derived correction through the
fixed-field path moves U *away* from DNS: error ratio 1.060, 1.072, 1.075 over 3 outer-loop
passes (gate ≤ 0.70, `configs/tolerances.yaml`). If the exact correction does not improve the
solved flow, a candidate's a-posteriori run cannot validate or refute it, so C is not run. This
confirms the pre-committed frozen-only fallback; every result stays labelled `frozen`.

**Results (same day, all `frozen`, exploratory):**

- **B1 Replication** (`runs/arms/replication-2026-11-02.json`, $6.00, complete): swarm
  0.888 ± 0.064, swarm_no_redteam 0.833 ± 0.071, sparse_baseline 0.828 ± 0.007. RP1 U = 4/25,
  exact one-sided p = 0.972; RP2 U = 1/25, p = 0.996. Neither hypothesis replicates. Swarm seed 51
  has no champion and scores 1.0 by the registered rule: in all 5 rounds the red-team screen broke
  every rung-1 survivor, so nothing reached rung 2. Pooled 10 seeds (descriptive only): swarm
  0.867 ± 0.050, swarm_no_redteam 0.845 ± 0.050, sparse_baseline 0.826 ± 0.006.
- **B2 Single LLM** (`runs/arms/control-single_llm-2026-11-02.json`, $1.78): 0.832 ± 0.022; vs
  swarm p = 0.21, vs swarm_no_redteam p = 0.048, vs sparse p = 0.73 (control better than the
  swarm arms in direction).
- **A3 Random grammar** (`runs/arms/control-random_grammar-2026-11-02.json`, $0.87):
  0.837 ± 0.016; vs swarm p = 0.56, vs swarm_no_redteam p = 0.044, vs sparse p = 0.95. Its
  champions converge to the same structures the swarm finds.
- **A2 Sparse + red team** (`runs/arms/analysis-a-2026-11-02.json`): mean ≈ 0.819, the lowest of
  all arms.
- **A1/A4/A5:** swarm champions are the most realizable off-train (≥ 99.1 % of convdiv points);
  the attack hills break 0/71 candidates while convdiv breaks 48/71, and broken candidates score
  *better* on curved_step (AUC 0.27), so the screen trades validation accuracy for convdiv
  robustness; the swarm keeps more structural diversity (5 distinct champion structures vs 2 for
  sparse).

Reading: on this metric the proposer (swarm, single LLM, random grammar) does not change the
outcome measurably; the fitter and the ladder dominate, and the convdiv red-team screen can
reject every candidate in a seed.

## 2026-11-02 — Exploratory run: swarm with SAM and red-team break ratio 1.10 (declared before running)

**Exploratory**, after the feature freeze; it does not replace the decision-run or replication
results and never touches `data/locked/`. Motivation: the convdiv screen broke 48/71 candidates
and every candidate of replication seed 51, and broken candidates score better on curved_step.

- Arm `swarm_sam_rt110`: the swarm arm (red team on) on current `main` (`b32611c`, which adds
  SAM-in-the-loop and Analyst v3) with `--sam` (Analyst error regions segmented by SAM 3.1) and
  the red-team break ratio raised from 1.0 to **1.10** on every probe case (attack hills broke
  0/71 at 1.0, so in practice this acts on convdiv). Everything else unchanged.
- Seeds 42–46, 5 rounds × 2 groups, budget $6, via `scripts/run_controls.py --control
  swarm_sam_rt110`; output `runs/arms/explore-sam_rt110-2026-11-02.json`. Its red-team breaks go
  to `runs/arms/explore-sam_rt110-attacks/`, not the permanent library.
- Comparison: exact one-sided Mann–Whitney vs the decision-run swarm, swarm_no_redteam and
  sparse_baseline (same seeds), descriptive. SAM, Analyst v3 and the threshold change together, so
  a difference cannot be attributed to one of them.

**Result (same day, `frozen`, exploratory):** `swarm_sam_rt110` ($3.81, complete, every seed has a
champion): 0.820 ± 0.034 (42: 0.843, 43: 0.761, 44: 0.839, 45: 0.827, 46: 0.833). Vs decision
swarm U = 19/25, p = 0.111 (better on 3 of 5 paired seeds); vs swarm_no_redteam U = 25/25,
p = 0.004; vs sparse_baseline U = 6/25, p = 0.925 (lower mean only because of seed 43; sparse
wins 19 of 25 pairs). The red team broke 30 of 66 rung-1 survivors (was every survivor in
replication seed 51); 20 of 25 rounds produced a champion. All five champions stay below SST on
convdiv (ratio 0.62–0.65). Seed 44's champion has extreme constants
(`div(964.265, -63.2677 + I1) * T1 + 2.94592 * tanh(964.615 * I2) * T2`), effectively a constant
T1 term plus a sign switch on T2. SAM, Analyst v3 and the threshold changed together, so the gain
over the decision swarm arm cannot be attributed to one of them; one exploratory run among several.
## 2026-11-02 — Constant-coefficient control (exploratory, **post hoc**) and a diagnosis of the arms

**Post hoc, not an RP result.** The control's form was chosen after a scratch probe
(`scratch/probe_representation_ceiling.py`, not committed) had looked at the validation and red-team
cases. It is reported so the arms can be read, never pooled into RP1/RP2, and it does not touch
`data/locked/`.

**Control** (`scripts/run_controls.py --control constant`, same protocol as the decision run: 5 rounds
× 2 groups, seeds 42–46, frozen; output `runs/arms/control-constant-2026-11-02.json`, $0.00, no model
calls): the proposer always returns constant-coefficient forms (`c1·T1 + c2·T2 + c3·T3` and two
subsets), the red team is stubbed with every available frozen flow, and fitter, ladder, realizability
gate, red-team screen and champion selection are unchanged. Every seed picks
`0.333·T1 − 3.05432·T2 + 1.5·T3`: train 0.636, **worst_validation_ratio 0.761** (spread 0, the arm is
deterministic), realizable on train, no red-team break (convdiv 0.617). Decision run for reference:
swarm 0.845 ± 0.018, swarm_no_redteam 0.858 ± 0.011, sparse_baseline 0.823 ± 0.004. The decision-run
JSON is not on this machine, so the script's exact p-values were not computed.

**Probe readings (scratch, not results):** per-point least squares on T1..T3 reproduces `a_delta`
exactly on every case (ratio 0.000), so the tensor basis is not the limit. Polynomial coefficients in
(I1, I2) fit train better (0.53 → 0.44) and validation worse (1.9, worse than SST); adding a wall
marker √k/(ωd) makes it worse still. On these cases the invariants carry little information that
transfers between geometries.

**Reading:** swarm champions are this constant model plus invariant terms that are mostly constants
in disguise (with I2 ≈ −0.04, `−35.2·I2·T3` ≈ `+1.4·T3`). Those terms lower the train ratio
(0.636 → ~0.58) and raise the validation ratio. Champion selection minimizes train ratio, the 3%
elegance band is measured on train, and `description_length` is called with no constants (0 bits per
constant), so the selection rule cannot pick the constant model. This explains why proposer choice
(swarm, single LLM, random grammar) does not change the outcome: more search fits train harder.

**Not changed:** the decision-run result, `configs/tolerances.yaml`, the splits, the selection rule
(feature freeze). Changing selection (e.g. leave-one-flow-out CV, constant bits in DL) is a new
protocol and would need its own registration.

## 2026-11-02 — Dollar limit is per session, not per round (bug fix)

`_run_round_live` built a fresh `ModelRuntime` every round, so `SESSION_LIMIT` ($50) only capped one
round, and the Board was always told `$0.00 / $50.00`. Each model call now logs its `dollars`, and a
round starts its runtime at `event_logger.session_spent(events.jsonl)`. `dollars_spent` in the round
result stays per round, so the running totals in `run_arms.py` and `run_control.py` are unchanged.
Sessions logged before this fix carry no `dollars` and count as $0 (under-count for legacy sessions
only). No scoring code changed; decision-run results are unaffected.

## 2026-11-03 — Held-out selection rule (`selection="heldout"`), registered before computing

**Why:** every filter that picks a candidate ranks by the train ratio on two near-identical hills
(rung-1 and rung-2 halving, round champion, seed champion, the 3% band), and the champion DL charges
0 bits per constant. More search therefore fits train harder (entry above). This rule picks on flows
the constants were not fitted on.

**Rule (opt-in; `selection="train"` stays the default and reproduces the decision run):**
- Selection flows S: every available frozen attack hill plus the `redteam` split. Never validation,
  never locked. Constants are still fitted on train only (attack flows are never training).
- Selection score = max(train ratio, ratio on every case in S); a non-finite or failed score is inf.
- Rung-1 and rung-2 halving rank by the selection score (still drop the bottom 50%); rung 0,
  realizability and the red-team screen are unchanged.
- Champion: within 3% of the best selection score (margin unchanged), lowest DL2, where
  DL2 = nodes·log2(V) + Σ bits(c); bits(c) = log2(|SNAP_CANDIDATES|) for a snapped value, else 16.
- Seed champion: lowest selection score across rounds.
- Metric unchanged: `worst_validation_ratio` on `curved_step`.

**Experiment E1 (exploratory, $0, no LLM):** the seeded `random_grammar` proposer, seeds 42–46,
5 rounds × 2 groups, red team stubbed with every available frozen flow, run twice: `selection=train`
and `selection=heldout`. Same proposal stream, so the difference is the selection rule only. Also the
`constant` control under `heldout` as a sanity check. Caveat: some validation numbers of candidates
are already known (entry above), so E1 is exploratory, not confirmatory.

**Consequence for RP1:** under `heldout`, both swarm arms select on S, so the no-red-team ablation
loses most of its contrast (only the exclusion screen differs). RP1 stays on the decision run.

**E1 result (2026-11-03, exploratory, frozen, $0, `runs/arms/e1-*.json`):** random_grammar with
`selection=train` 0.837 ± 0.016, with `selection=heldout` 0.833 ± 0.025. Only seed 42 changed its
champion (0.811 → 0.791); the other four picked the same expression. Constant control under
`heldout`: 0.761 on every seed (unchanged).

**Why the rule does not help, and a correction to the reading above:** on every non-validation flow
(both train hills, the α 0.5/0.8/1.2 hills, convdiv) the invariant-dependent champions beat the
constant model (e.g. 0.54–0.60 vs 0.62–0.65); they lose only on `curved_step` (0.83–0.85 vs 0.761).
So the invariant terms are not train noise: they transfer to the hill family and to convdiv, and
`curved_step` is the one flow where they backfire. The constant model's advantage is visible only on
the validation case, so no selection that respects the splits can find it, and a single validation
case cannot say which behavior the locked flows will show. `selection="heldout"` stays as an opt-in
option; the default is unchanged.

## 2026-11-03 — Data v3: bumps and flat plates join training (registered before computing)

**Why:** with two hills as the only training flows, every flow available for fitting or selection
says the same thing, and none predicts `curved_step`. A scratch probe on the curated dataset's
unused families (`scratch/probe_family_cv.py`, never loads `curved_step` or locked data) found the
best constant coefficients differ strongly by flow (T2: hills −3.05, convdiv −4.13, flat plate
−5.16, bumps −1.94 → −0.30 with bump height; T1 ≈ 0.25 everywhere). Fitted on hills + bumps +
convdiv + flat plate together, a quadratic g(I1, I2) gets every family below SST (worst 0.73);
the constant model does not (bumps 1.46). The invariant terms carry real cross-flow information
that two hills cannot pin down.

**Change (same CC-BY-4.0 Kaggle files, same `extract_case_arrays` pipeline):**
- `train` += parametric bumps `bump_h20`, `bump_h31`, `bump_h42` and the nine zero-pressure-gradient
  flat plates `flat_plate_re1000` … `flat_plate_re4060` (the spec's canonical "do no harm" suite).
- `redteam` += `bump_h26`, `bump_h38` (interpolation hold-outs inside the bump family) and
  `converging_diverging_channel_re20580`.
- Unchanged: `curved_step` (validation), `converging_diverging_channel` (redteam), the attack hills,
  the locked cases. The other 15 square-duct Reynolds numbers stay out (same family as locked).
- Hold-outs chosen by the rule "alternate bumps, keep both ends in training" before any score on
  `curved_step` was computed for data v3.

**Consequence:** a new protocol. Results under data v3 are labelled `data=v3` and never pooled with the
decision run (data v2). Experiment E2 ($0, no LLM): sparse baseline, constant control and
`random_grammar` (red team stubbed), seeds 42–46, 5 rounds × 2 groups, `selection=train`.

**E2 result (2026-11-03, exploratory, frozen, `data=v3`, $0, `runs/arms/e2-v3-*.json`),
`worst_validation_ratio` on `curved_step`, seeds 42–46:**
- sparse_baseline 0.748 ± 0.028 (data v2 decision run: 0.823 ± 0.004)
- random_grammar (red team stubbed) 0.784 ± 0.055 (data v2, E1: 0.837 ± 0.016)
- constant control 0.943 (data v2: 0.761)

Reading: wider training data lowers validation error for every model with invariant dependence, and
removes the constant model's edge, as the family probe predicted. Still frozen a priori on one
validation case; the solver oracle gate is still red, so nothing here is a flow-level (`full`)
claim. The swarm arms under data v3 have not been run (they need paid API calls).

## 2026-11-03 — E3: swarm arms on data v3 (declared before running, paid API)

**Exploratory**, `data=v3`, frozen. The decision-run command on data v3 and current code:
`scripts/run_arms.py --rounds 5 --groups 2 --seeds 42,43,44,45,46 --budget-usd 12`, `selection=train`,
SAM off, red-team break ratio 1.0 (unchanged). Arms: swarm, swarm_no_redteam, sparse_baseline.
Red-team breaks go to `runs/arms/explore-v3-swarm-attacks/`, not the permanent library. Earlier
data-v2 session folders moved to `runs/_archive-v2-2026-11-03/` so no round reads data-v2 history.
Output `runs/arms/e3-v3-arms.json`. Metric: `worst_validation_ratio` on `curved_step`; compared
descriptively with E2 (same data) and the decision run (data v2, not pooled).

**E3 restart (same day):** the first launch ran ~5 min per round, so its 7000 s timeout would have
cut it mid-arm. It was stopped after 3 rounds of swarm seed 42 ($0.62, discarded, sessions in
`runs/_archive-e3-partial-2026-11-03/`) and relaunched as one process per seed
(`scratch/arms_seed.py <seed> e3-v3 v1 2.4`: the same `run_arms.collect_swarm_arm` for swarm then
swarm_no_redteam, $2.40 cap per seed = $12 total), outputs `runs/arms/e3-v3-s<seed>.json`. Protocol
otherwise unchanged.

## 2026-11-03 — Loop v2 and E4 (registered before any v2 result)

**Loop v2** (`flowforge/orchestrator/loop_v2.py`, opt-in `run_arms.py --loop v2`; `round.py`
unchanged): diagnostician (LLM, replaces Board + Analyst, runs first, reads the population's per-flow
train and held-out ratios) → theorist_v2 × G (3 proposals each from the diagnosis) → fit + score
(one deterministic node: constants on train, per-case train ratios, held-out ratios on attack hills +
redteam split, realizability) → reviser (same group sees its own per-case scores, revises once) →
population (top 8, at most 2 per tensor set, carried across rounds in the event log) → champion (same
3% / DL rule; avoids broken candidates when any unbroken one exists). Coder, Composer, Skeptic and the
LLM red team are not dispatched; the red team is a held-out score column. No LLM context contains
validation (unit test). Seed champion = the last round's champion (the population is cumulative).
Prompts `diagnostician`, `theorist_v2`, `reviser` v1. Smoke run on data v3 with a fake LLM: 15 s per
round.

**E4 (not yet run; needs paid API approval):** loop v2 on data v3, same seeds 42–46, 5 rounds ×
2 groups, swarm and swarm_no_redteam, $12 cap, compared with E3 (loop v1, same data and seeds),
E2 sparse and random grammar. Metric unchanged (`worst_validation_ratio`, `curved_step`). The
question: does the topology let the LLM beat sparse regression and random search?

**E3 result (2026-11-03, exploratory, frozen, `data=v3`, loop v1, $6.43, `runs/arms/e3-v3-s4*.json`),
`worst_validation_ratio` on `curved_step`:** swarm 0.939 ± 0.035, swarm_no_redteam 0.883 ± 0.043; every
seed has a champion. Against E2 on the same data and seeds: sparse_baseline 0.748 ± 0.029 and
random_grammar 0.784 ± 0.055 beat both swarm arms on every pair (U = 0, exact one-sided p = 1.0 for
"swarm better"). Swarm vs swarm_no_redteam U = 3/25 (p = 0.984 for "red team better"): with the
v3 red-team split (bumps h26/h38, convdiv Re 20580) the screen at ratio 1.0 removes candidates that
score better on validation. Loop v1 does not use the wider data; the LLM proposer in this topology
adds nothing measurable.

**E4 result (2026-11-03, exploratory, frozen, `data=v3`, loop v2, $6.79, `runs/arms/e4-v2-s4*.json`),
`worst_validation_ratio` on `curved_step`:** swarm 0.850 ± 0.105, swarm_no_redteam 0.869 ± 0.116; every
seed has a champion. Vs loop v1 (E3, same data and seeds): swarm U = 20/25, exact one-sided p = 0.075;
no-red-team U = 11/25, p = 0.655. Vs E2: sparse_baseline (0.748) U = 5/25, p = 0.952; random_grammar
(0.784) U = 7/25 and 6/25. Seed 46 reached 0.694 (swarm) and 0.688 (no red team) with the same structure
found independently, `0.26·T1 + (−7.4 + 7.3·tanh(12.4·I1))·T2 + 3.6·exp(−1.3·I1)·T3`, the lowest of
any arm; the arms' means still trail sparse and random grammar.

**Why loop v2 stalls after round 1 (event logs, all 10 sessions):** of the candidates proposed in
rounds 2–5, 121 were `invalid` (round 1: 3), almost all over the 25-node cap (26–32 nodes): the
Theorist extends population members that are already near the cap, and neither node counts nor the
parser's message reach it (the Reviser sees only `status: invalid`). 147 more were non-realizable, and
30 of 262 calls returned empty text (8192-token completion limit spent on reasoning; swarm seed 46 had
no proposals in rounds 3–5). These are wiring defects of loop v2, not evidence about the topology.

## 2026-11-03 — Loop v2.1 and E5 (registered before running)

**Loop v2.1** (fixes for the E4 stall; topology unchanged): completion limit 50,000 tokens for the v2
roles (probe: the API accepts it), up from the dispatcher's 8,192; an `invalid` candidate carries the
parser's message (e.g. "Complexity 27 exceeds cap 25") to the Reviser and the rejected list; every
candidate the LLM sees carries `nodes`, `realizable` and `realizable_fraction`, and every v2 context
carries `max_nodes: 25`. Prompts `theorist_v2` and `reviser` v2 tell the model to replace rather than
add terms near the cap and how to read the new fields.

**E5:** loop v2.1, data v3, seeds 42–46, 5 rounds × 2 groups, swarm and swarm_no_redteam,
`scratch/arms_seed.py <seed> e5-v21 v2 3.0` ($3.00 cap per seed = $15), outputs
`runs/arms/e5-v21-s<seed>.json`; E4 sessions moved to `runs/_archive-e4-2026-11-03/` first.
Compared with E4 (v2), E3 (v1), E2 sparse and random grammar on the same data and seeds; metric
unchanged.


## 2026-11-03 — Locked milestone 1 (option B), candidate set fixed before the vault is opened

**Rule:** per approach, the champion with the lowest `curved_step` validation ratio among COMPLETED
data-v3 runs (E2 sparse and random grammar, E3 loop v1, E4 loop v2; E5 excluded because it was still
running), as trained; plus the same structure with constants refit on all non-locked data (train,
validation, redteam, attack hills; 22 cases, 4000 points each, non-finite rows
dropped as in `score_expression`); the sparse baseline refit on the same data with its picked seed;
the constant form refit on all data; and the post-hoc data-v2 constant model as a reference.
Picked: sparse_v3 (seed 43, curved_step 0.733), random_grammar_v3 (seed 43, curved_step 0.730), loop_v1_v3 (seed 46, curved_step 0.851), loop_v2_v3 (seed 46, curved_step 0.688). Built by `scratch/build_milestone.py`; files `runs/arms/milestone1-candidates.json`
and `milestone1-meta.json`.

**Evaluation:** ONE call, `scripts/evaluate_locked.py --milestone 1 --candidates-file
runs/arms/milestone1-candidates.json` (one log line for the whole set). Metric: frozen a-priori
error ratio on each locked case (same scorer as validation). Only `square_duct` is present on this
machine; `nasa_wall_mounted_hump` is not ingested here. This machine's vault log shows 0 prior
locked evaluations; the other machine's count was not available. `square_duct` is 3-D (secondary
flow), where the 2-D-only exclusions of the grammar (T4, I3–I5) are a known limitation.

**Candidates (10):**
- `sparse_v3`: `3.765 * T3 + (-3.491) * tanh(I1) * T3 + 3.277 * tanh(I1) * T2 + (-2.974) * T2`
- `random_grammar_v3`: `((-2.32717) * exp(-I1)) * T2 + ((-2.73102) * I2) * T1 + (div(3.43418, 0.879777 + I1)) * T3`
- `loop_v1_v3`: `0.152437 * tanh(I1) * T1 + (-0.521252) * T2 + div(2.33143, 0.878462 + I1) * T3`
- `loop_v2_v3`: `0.255839*T1 + ((-7.49174) + (+7.35441)*tanh(12.4939*I1))*T2 + (3.89159*exp((-1.5)*I1))*T3`
- `constant_v2data_posthoc`: `0.333 * T1 + (-3.05432) * T2 + 1.5 * T3`
- `random_grammar_v3_refit_all`: `((-3.05782) * exp(-I1)) * T2 + ((-2) * I2) * T1 + (div(3.5236, 1 + I1)) * T3`
- `loop_v1_v3_refit_all`: `0.333 * tanh(I1) * T1 + (-1.5) * T2 + div(3.52784, 1 + I1) * T3`
- `loop_v2_v3_refit_all`: `0.25459*T1 + ((-7.76313) + (+7.60746)*tanh(12.7347*I1))*T2 + (3.96842*exp((-1.46096)*I1))*T3`
- `constant_refit_all`: `0.129433 * T1 + (-0.205567) * T2 + 0.242094 * T3`
- `sparse_refit_all`: `3.638 * tanh(I1) * T2 + (-3.286) * T2 + 0.8313 * T3 + 0.2515 * T1`

**Milestone 1 result (2026-11-03, locked, frozen a priori, `square_duct` only; vault log: evaluation 1
of 3 on this machine):** loop_v2_v3 0.527 (refit on all data 0.520); constant_v2data_posthoc 0.610;
sparse_v3 0.618 (refit 0.619); random_grammar_v3 0.658 (refit 0.607); loop_v1_v3 0.882 (refit 0.754);
constant_refit_all 0.957. The validation ranking held on the locked case: loop v2's champion is best on
both, loop v1's worst on both. One locked case, one champion per approach (best validation seed, the
same rule for every approach), frozen a priori: not a flow-level claim and not a seed-averaged one
(seed averages on validation: loop v2 0.850–0.869 vs sparse 0.748).

**E5 result (2026-11-03, exploratory, frozen, `data=v3`, loop v2.1, $6.86, `runs/arms/e5-v21-s4*.json`,
combined table `runs/arms/data-v3-summary.json`), `worst_validation_ratio` on `curved_step`:** swarm
0.868 ± 0.046, swarm_no_redteam 0.871 ± 0.032; every seed has a champion; 0 empty replies. Vs loop v2 (E4)
U = 13/25, p = 0.500 (same mean, spread 0.105 → 0.046); vs loop v1 (E3) U = 22/25, p = 0.028; vs
sparse_baseline U = 0/25 (sparse better on every pair). The v2.1 fixes made later rounds productive
but did not move the mean on this validation flow. Scripts used for E3–E5 and milestone 1 now live in
`scripts/` as identical copies (`run_arms_seed.py`, `build_milestone_set.py`, `summarize_data_v3.py`).

## 2026-11-03 — Loop v3: the LLM proposes features, a deterministic search writes the formula (declared before running)

Branch `explore/llm-features`, exploratory, `frozen`; v1, v2 and the 25-node main protocol are untouched.
Motivation: loop v1/v2 seed means trail sparse, random grammar and a deterministic greedy search, so the
LLM is moved from inventing formulas to proposing physics inputs.

- **Features:** `flowforge/data/features.py` computes, from the raw k-omega SST rows (row-aligned with the
  processed stores, checked), 10 standard bounded features (after Ling & Templeton 2015, Wang et al. 2017)
  and 15 dimensional primitives; stored in `data/features/<case>.npz` (not committed). Locked cases are
  never featurized.
- **Feature language** (`flowforge/data/feature_dsl.py`): whitelisted primitives and functions; a feature is
  accepted only if dimensionless (unchanged when velocities ×2 and lengths ×3), finite on ≥ 99 % of train
  points and not constant; mapped to x / (|x| + median|x|).
- **Search** (`flowforge/search/omp.py`): greedy forward selection of f(v)·T_k terms (v, v², tanh and
  Gaussian windows, products with I1, I2), least squares on the data-v3 train split (3000 points per case),
  largest formula within **40 nodes**. Realizability is reported, not enforced (same for every arm).
- **Loop v3** (`flowforge/orchestrator/loop_v3.py`, role `physicist`, prompt v1): per round the LLM sees the
  active features with their held-out gain (search re-run without each), the best formula and its train and
  held-out (redteam split) ratios, and rejected features with reasons; proposes 1–3 features, may drop
  some; at most 10 active. Champion = round with the lowest worst held-out ratio; validation never enters
  any context or selection.
- **Control 2** (already run, no API, `scripts/control2_features.py`): same search, curved_step at ≤ 40
  nodes: invariants only (I1, I2) 0.728; I1, I2 + standard features 0.670.
- **Run:** `scripts/run_loop_v3.py --tag v3 --seeds 42,43,44,45,46 --rounds 5`; output
  `runs/arms/loop-v3-v3-<seed>.json` (one process per seed). Primary comparison: curved_step of the LLM-feature champion vs control
  "standard" (0.670) at the same cap; the LLM adds value only if it beats the textbook features.
  Secondary: LLM + standard features together.

**Loop v3 result (2026-11-03, exploratory, frozen, $0.81, `runs/arms/loop-v3-v3-<seed>.json`, ≤ 40 nodes):**
curved_step 0.705 ± 0.012 (42: 0.693, 43: 0.695, 44: 0.705, 45: 0.724, 46: 0.706). Better than the
invariants-only control (0.728) on 5/5 seeds, worse than the standard-features control (0.670) on 5/5.
LLM + standard features together: 0.703 ± 0.013 (the greedy search picks the LLM features first).
On the held-out redteam flows used for selection (mean of the 4 ratios) the LLM champions are equal to or
better than the standard control: 0.460–0.490 vs 0.484 (worst case 0.501–0.545 vs 0.544). All 75 proposed
features passed the dimensional check; `Pk / eps` (non-equilibrium) was proposed in every seed.
Reading: the LLM's features are physically sensible and carry information beyond I1, I2, and they match or
beat the textbook set on the selection flows, but not on curved_step; with one validation flow the
ranking between feature sets is not settled.

## 2026-11-03 — Loop v3 long runs (declared before running)

Same loop v3, code, prompt (physicist v1), cap (40 nodes), splits and controls as above; seeds 42–46,
**15 rounds** per session, one process per seed and arm:
- `v3long`: starts with no features, at most 10 active (as the 5-round run, three times longer);
- `v3seed`: starts with the 10 standard features active (`--seed-standard`), at most 16; the LLM may add
  features and drop any, standard ones included. Question: can the LLM improve on the textbook set?
Outputs `runs/arms/loop-v3-v3long-<seed>.json`, `runs/arms/loop-v3-v3seed-<seed>.json`. Champion = round
with the lowest worst held-out ratio (validation never used). Note from the dry run: adding two fixed
features to the standard set moves curved_step from 0.670 to 0.692 at the same cap (the greedy search
picks terms that fit train better), so more features are not automatically better.

**Long-run result (2026-11-03, exploratory, frozen, $4.88, ≤ 40 nodes, 15 rounds):**
- `v3long`: curved_step 0.704 ± 0.015 (0.687–0.724), the same as the 5-round run (0.705 ± 0.012); held-out
  mean of the 4 selection flows 0.461 (5-round 0.474; standard control 0.484).
- `v3seed`: curved_step 0.692 ± 0.009 (0.684–0.708), worse than the standard set alone (0.670) on 5/5 seeds;
  held-out mean 0.454, better than the standard control (0.484) on 5/5 seeds. The LLM dropped most standard
  features in 3 of 5 seeds (1 kept) and kept 8–9 in the other 2.
Reading: three times more rounds did not move curved_step. Every LLM arm improves the held-out flows it is
selected on and loses on curved_step, so the selection flows (convdiv, bumps) and the single validation flow
reward different corrections; with one validation flow it cannot be told which ranking generalizes.

## 2026-11-03 — 29 parameterized hills: baseline built here, split fixed before any score

**Data:** Xiao, Wu, Laizet & Duan (2020), 29 DNS of periodic hills at Re_H 5600 (NASA TMR zip, 1.2 GB,
`scratch/downloads/hills29/`; no license stated, cite the paper). DNS only, so the k-omega SST baseline is
computed here (`flowforge/data/hills29.py`): terrain-following mesh from the DNS immersed-boundary wall
(displaced block mesh, 20 cells per H in x, 80 in y graded to both walls), simpleFoam kOmegaSST, nu = 1/5600,
forcing for crest bulk velocity 1, low-Re wall conditions, run to residuals 1e-5/1e-6; DNS statistics
interpolated (linear) onto the RANS cell centres; cells whose stencil touches the solid are dropped. Arrays and
features use the same code and conventions as the McConkey ingest (checked: gradU_ij = du_i/dx_j,
eps = 0.09 k omega). Check on the baseline geometry (alpha 1, Lx 9, Ly 3.036) against McConkey's
`periodic_hill_re5600`: separation x 0.98–7.67 vs 0.96–7.59; sparse_v3 champion ratio 0.674 vs 0.673;
loop_v2 champion 0.577 vs 0.599. Stores `data/processed/hill29_*`, features `data/features/hill29_*.npz`.

**Split (rule fixed now, before any candidate is scored on these cases):** the 27 grid cases (alpha 0.5/1/1.5
× three bottom lengths × three heights Ly 2.024/3.036/4.048) are split by a Latin square, one held-out
(length, height) pair per alpha so each length and each height appears once per alpha; the two interpolation
slopes alpha 0.75 and 1.25 are held out too. **Validation (11):** alph05-4071-2024, alph05-7071-3036,
alph05-10071-4048, alph10-6-3036, alph10-9-4048, alph10-12-2024, alph15-7929-4048, alph15-10929-2024,
alph15-13929-3036, alph075-80355-3036, alph125-99645-3036. **Train (18):** the other grid cases.
Note: alph05-7071-3036 matches the geometry of the McConkey attack hill alpha 0.5 (a loop-v2 selection case;
loop v3 does not use attack hills).

**Evaluation plan:**
(a) no API: re-fit every existing arm exactly as before (data-v3 train) and score it on the 11 validation hills
(controls invariants and standard, and the champion feature sets of loop v3 `v3`, `v3long`, `v3seed`);
(b) data v4 = data-v3 train + the 18 train hills: controls and loop v3 (5 rounds, seeds 42–46) re-run.
Metric per arm: mean and worst ratio over the 11 hills; curved_step reported separately.

**Hills, plan (a) result (no API, `runs/arms/hills29-eval-a.json`; every arm fitted on data-v3 train exactly as
before, champions rebuilt from saved formulas and checked to reproduce their curved_step to 1e-9):** mean ratio over
the 11 validation hills (worst in brackets): invariants 0.572 (0.648); standard features 0.572 (0.666); loop v3
`v3` 0.574 ± 0.008; `v3long` 0.560 ± 0.022 (best seed 0.521); `v3seed` 0.555 ± 0.026 (seeds 42/44 0.526/0.527).
The standard set's curved_step advantage (0.670 vs 0.728) does not carry to the hills. Across the 15 LLM sessions
the selection flows' mean predicts the hills' mean (Spearman 0.59, p = 0.020); curved_step predicts neither
(−0.03 with the hills, −0.04 with the selection flows). curved_step alone was not a representative validation.

**Plan (b) settings:** data v4 (registry `configs/cases_v4.yaml`, opt-in via `FLOWFORGE_CASES`) train = data-v3 train + 18 train hills, 1500 points per case (memory), validation =
curved_step + 11 hills (reported separately), selection = redteam split (unchanged), 40 nodes, 5 rounds, seeds
42–46, arms `v4` (no initial features) and `v4seed` (standard set seeded, at most 16). Controls are recomputed
on the same data inside each run.

**Plan (b) result (2026-11-03, exploratory, frozen, $1.58, `runs/arms/loop-v3-v4*-<seed>.json`, data v4, ≤ 40
nodes):** mean ratio over the 11 validation hills (worst in brackets). Controls on the same data: invariants
0.571 (0.635), standard features 0.529 (0.580). Loop v3 `v4` (LLM features only): 0.504 ± 0.036 (42: 0.556,
43: 0.518, 44: 0.500, 45: 0.457, 46: 0.491), below the standard control in 4/5 seeds and below invariants in
5/5; worst case below standard in 3/5. `v4seed`: 0.499 ± 0.037 (seed 42 kept the standard set unchanged,
0.529; three seeds 0.465–0.489; seed 46 0.546). curved_step for every arm trained on v4 is worse than on v3
(controls 0.767/0.771, `v4` 0.746 ± 0.042): with the hills dominating the training points, the fitted
corrections suit the hills more than the backward step.
Reading (exploratory, after the decision run): with 11 validation flows the LLM's physics features beat the
textbook set on average (−5 %, best seed −14 %), but the 4/5 sign is not significant (one-sided sign test
p = 0.19) and seed spread (± 0.036) is as large as the gap.
