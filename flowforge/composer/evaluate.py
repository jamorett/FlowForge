"""Composer evaluation (S6.2): gated composition scored on training flows.

Every active gate pays +16 bits. Composition must beat the best single
module on worst-case (minimax) error or it is rejected (RP4 cut rule).
"""

from __future__ import annotations

import numpy as np

from flowforge.composer.gates import GATE_DL_PENALTY_BITS, compose


def evaluate_composition(modules: list[np.ndarray], gate_inputs: list[np.ndarray],
                         targets: list[np.ndarray], w: float, b: float) -> dict:
    assert len(modules) >= 2, "composer needs at least two modules"
    assert len(modules) == len(targets) == len(gate_inputs)
    preds, penalties = [], 0.0
    for i in range(0, len(modules) - 1):
        pred, penalty = compose(modules[i], modules[i + 1], gate_inputs[i], w, b)
        preds.append(pred)
        penalties += penalty
    errors = [float(np.mean((p - t) ** 2)) for p, t in zip(preds, targets)]
    single_errors = [float(np.mean((m - t) ** 2)) for m, t in zip(modules, targets)]
    return {
        "worst_error": max(errors),
        "best_single_worst": max(single_errors),
        "dl_penalty_bits": penalties,
        "beats_single": max(errors) < max(single_errors),
        "n_gates": len(preds),
    }
