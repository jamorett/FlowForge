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
