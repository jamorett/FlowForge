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
