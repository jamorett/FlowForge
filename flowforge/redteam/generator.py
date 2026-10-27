"""Red-team flow generator (S6.1). Validation only, never training.

Hill steepness alpha is restricted to [0.5, 1.5] and Reynolds numbers are
swept over positive values. Every generated spec carries split="validation"
so it can never be routed into training; broken candidates are persisted by
flowforge.redteam.attacks.record_attack under library/attacks/.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ALPHA_MIN, ALPHA_MAX = 0.5, 1.5
ALLOWED_KINDS = ("periodic_hill", "bump")


@dataclass(frozen=True)
class FlowSpec:
    kind: str
    alpha: float  # hill steepness multiplier, in [0.5, 1.5]
    reynolds: float
    split: str = "validation"

    def __post_init__(self) -> None:
        assert self.kind in ALLOWED_KINDS, f"unknown attack kind {self.kind!r}"
        assert self.split == "validation", "red-team flows are validation only, never training"
        assert math.isfinite(self.alpha) and ALPHA_MIN <= self.alpha <= ALPHA_MAX, (
            f"alpha {self.alpha} outside [{ALPHA_MIN}, {ALPHA_MAX}]"
        )
        assert math.isfinite(self.reynolds) and self.reynolds > 0, "Reynolds must be positive"


def generate_attacks(alphas=(0.5, 0.75, 1.25, 1.5), reynolds=(5600, 10595, 20000),
                     kinds=("periodic_hill",)) -> list[FlowSpec]:
    """Cross product of hill alphas x Reynolds sweep. Validation only."""
    assert alphas and reynolds and kinds, "empty sweep"
    specs = [FlowSpec(k, float(a), float(r)) for k in kinds for a in alphas for r in reynolds]
    assert all(s.split == "validation" and s.kind != "train" for s in specs)
    assert all(ALPHA_MIN <= s.alpha <= ALPHA_MAX for s in specs)
    return specs
