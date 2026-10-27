"""Permanent attack suite (S6.1/Phase 3).

Every attack that ever broke a candidate is stored under library/attacks/
and re-run against all verified modules. Generated flows are validation
only; this module refuses training-split specs by construction.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from flowforge.ladder.ladder import apriori_mse

ATTACK_DIR = Path("library/attacks")


def record_attack(spec: dict, candidate: str, broke: bool,
                  attack_dir: Path = ATTACK_DIR) -> Path | None:
    if not broke:
        return None
    assert spec.get("split", "validation") != "train", "attacks are never training flows"
    attack_dir.mkdir(parents=True, exist_ok=True)
    path = attack_dir / f"attack_{candidate[:8]}.json"
    path.write_text(json.dumps({"spec": spec, "candidate": candidate}),
                    encoding="utf-8")
    return path


def run_attack_suite(pred_fn, invariants, basis,
                     targets: dict[str, np.ndarray]) -> dict[str, float]:
    """Score one candidate on every validation target. Returns per-flow MSE."""
    scores: dict[str, float] = {}
    for flow_id, target in targets.items():
        pred = pred_fn(invariants, basis)
        scores[flow_id] = apriori_mse(pred, target)
    return scores


def broke_threshold(scores: dict[str, float], baseline: dict[str, float],
                    margin: float = 1.5) -> bool:
    """Broken = worse than 1.5x baseline on any generated flow."""
    return any(scores[f] > margin * baseline[f] for f in baseline if f in scores)
