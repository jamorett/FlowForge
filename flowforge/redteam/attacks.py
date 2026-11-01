"""Permanent attack suite (S6.1 / Phase 5.2).

Every attack that ever broke a candidate is stored under library/attacks/
and re-run against all verified modules. Generated flows are validation
only; this module refuses training-split specs by construction.

Attack pipeline (Phase 5.2 remediation):
  1. generate_attacks() proposes parameterized flow specs (alpha, Re).
  2. For each spec, build synthetic frozen-RANS fields via the invariant
     engine (no Docker needed for a-priori attacks).
  3. Score the champion candidate's prediction against the SST baseline.
  4. If champion error > 1.5 * baseline error on any flow, record the
     attack as a permanent regression case in library/attacks/.
  5. All future candidates must pass the permanent attack suite.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import numpy as np

from flowforge.ladder.ladder import apriori_mse

logger = logging.getLogger(__name__)

ATTACK_DIR = Path("library/attacks")
BREAK_MARGIN = 1.5


def record_attack(spec: dict, candidate: str, broke: bool,
                  attack_dir: Path = ATTACK_DIR) -> Path | None:
    """Record a successful attack (one that broke the candidate).

    Returns the path to the recorded attack JSON, or None if the
    candidate survived. Attacks carry split="validation" and are
    never used as training data.
    """
    if not broke:
        return None
    assert spec.get("split", "validation") != "train", "attacks are never training flows"
    attack_dir.mkdir(parents=True, exist_ok=True)
    # Use a content hash so re-running doesn't duplicate the same attack.
    content = json.dumps({"spec": spec, "candidate": candidate}, sort_keys=True)
    h = hashlib.sha256(content.encode()).hexdigest()[:12]
    path = attack_dir / f"attack_{h}.json"
    path.write_text(content, encoding="utf-8")
    logger.info("Attack recorded: %s (candidate=%s)", path.name, candidate[:30])
    return path


def run_attack_suite(pred_fn, invariants: dict[str, np.ndarray],
                     basis: dict[str, np.ndarray],
                     targets: dict[str, np.ndarray]) -> dict[str, float]:
    """Score one candidate on every validation target. Returns per-flow MSE.

    pred_fn: callable(invariants, basis) -> np.ndarray prediction.
    targets: dict mapping flow_id -> target tensor array.
    """
    scores: dict[str, float] = {}
    for flow_id, target in targets.items():
        pred = pred_fn(invariants, basis)
        scores[flow_id] = apriori_mse(pred, target)
    return scores


def broke_threshold(scores: dict[str, float], baseline: dict[str, float],
                    margin: float = BREAK_MARGIN) -> bool:
    """Broken = worse than 1.5x baseline on any generated flow."""
    return any(scores[f] > margin * baseline[f] for f in baseline if f in scores)


def score_champion_against_attacks(
    champion_expr: str,
    attack_specs: list[dict],
    attack_dir: Path = ATTACK_DIR,
) -> dict:
    """Score a champion expression against a set of attack flow specs.

    For each attack spec, generates synthetic frozen-RANS fields with
    the spec's parameters (alpha, reynolds), evaluates the champion's
    a-priori prediction, and compares to a baseline (zero-correction SST).

    Args:
        champion_expr: The DSL expression string for the champion candidate.
        attack_specs: List of dicts with keys: kind, alpha, reynolds.
        attack_dir: Where to record attacks that break the champion.

    Returns:
        dict with: n_attacks, n_broke, broke_specs, attack_scores.
    """
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.physics.tensors import invariants, normalized_tensors, tensor_basis

    n_broke = 0
    broke_specs: list[dict] = []
    attack_scores: list[dict] = []

    for spec in attack_specs:
        alpha = spec.get("alpha", 1.0)
        reynolds = spec.get("reynolds", 5600)
        kind = spec.get("kind", "periodic_hill")

        # Generate parameterized frozen-RANS fields.
        # Scale the velocity gradient magnitude by alpha and Reynolds:
        #   grad_u ~ alpha * Re^0.5 (characteristic strain rate scaling)
        #   omega ~ Re^0.5 / alpha (turbulence frequency scaling)
        rng = np.random.default_rng(int(alpha * 1000 + reynolds))
        n = 64
        scale = alpha * (reynolds / 5600.0) ** 0.5
        grad_u = scale * 0.1 * rng.standard_normal((n, 3, 3))
        omega = np.full(n, max(2.0 / alpha, 0.5))

        s, w = normalized_tensors(grad_u, omega)
        inv = invariants(s, w)
        bas = tensor_basis(s, w)

        # Baseline target: SST prediction (zero correction, a_delta = 0)
        target_zero = np.zeros((n, 3, 3))

        # Score champion prediction
        try:
            pred = candidate_anisotropy(champion_expr, inv, bas)
            champion_mse = float(np.mean((pred - target_zero) ** 2))
        except Exception as exc:
            champion_mse = 1e6
            logger.warning("Champion eval failed on attack %s: %s", spec, exc)

        # Baseline score: SST (zero correction) vs itself = 0
        # A non-trivial baseline: use 0.5*T1 (standard linear correction)
        baseline_pred = 0.5 * bas["T1"]
        baseline_mse = float(np.mean((baseline_pred - target_zero) ** 2))
        baseline_mse = max(baseline_mse, 1e-10)  # Guard division by zero

        ratio = champion_mse / baseline_mse
        broke = ratio > BREAK_MARGIN

        flow_id = f"{kind}_a{alpha:.2f}_Re{reynolds}"
        attack_result = {
            "flow_id": flow_id,
            "spec": spec,
            "champion_mse": champion_mse,
            "baseline_mse": baseline_mse,
            "ratio": ratio,
            "broke": broke,
        }
        attack_scores.append(attack_result)

        if broke:
            n_broke += 1
            broke_specs.append(spec)
            record_attack(
                {**spec, "split": "validation", "flow_id": flow_id},
                champion_expr,
                broke=True,
                attack_dir=attack_dir,
            )

    return {
        "n_attacks": len(attack_specs),
        "n_broke": n_broke,
        "broke_specs": broke_specs,
        "attack_scores": attack_scores,
    }


def load_permanent_attacks(attack_dir: Path = ATTACK_DIR) -> list[dict]:
    """Load all permanently recorded attacks from disk."""
    if not attack_dir.exists():
        return []
    attacks: list[dict] = []
    for f in sorted(attack_dir.glob("attack_*.json")):
        try:
            attacks.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return attacks
