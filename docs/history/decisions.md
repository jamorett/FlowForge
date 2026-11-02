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
