"""Composer evaluation (S6.2): gated composition scored on training flows.

Every active gate pays +16 bits. Composition must beat the best single
module on worst-case (minimax) error or it is rejected (RP4 cut rule).

The modules are composed sequentially into one joint composite field::

    composite = modules[0]
    composite = compose(composite, modules[i + 1], gate_inputs[i], w, b)

and that single composite is then scored against *every* target (training
flow). No target is silently dropped. The best-single comparand is likewise
honest: each single module is scored against every target, and the best
single is the module with the smallest worst-case error over all flows.

Length contract (all raise ``ValueError`` on mismatch):

* ``len(modules) >= 2`` and ``len(targets) >= 1``;
* ``len(modules) == len(targets)`` (the aligned-list contract this module
  has always asserted, now as ``ValueError`` instead of ``AssertionError``);
* ``len(gate_inputs)`` is ``len(modules) - 1`` (one gate per composition
  step) or ``len(modules)`` (the historical aligned form; the final gate
  input is validated for finiteness, the composition steps use the first
  ``len(modules) - 1`` gate inputs).
"""

from __future__ import annotations

import numpy as np

from flowforge.composer.gates import compose
from flowforge.elegance.engine import description_length


def evaluate_composition(modules: list[np.ndarray], gate_inputs: list[np.ndarray],
                         targets: list[np.ndarray], w: float, b: float,
                         base_dl: float = 0.0, n_nodes: int | None = None,
                         constants: list[float] | None = None) -> dict:
    """Score a gated composition on all training flows.

    Optional description-length wiring: ``base_dl`` is the ungated
    description length of the composite (default ``0.0``), or pass
    ``n_nodes``/``constants`` to compute it with
    :func:`flowforge.elegance.engine.description_length`. The returned
    ``composite_dl`` (aliases ``dl``, ``total_dl``, ``effective_dl``) is
    that base plus the accumulated 16-bit-per-gate penalty, so a gated
    composite always pays for its gates in champion selection.
    """
    if len(modules) < 2:
        raise ValueError("composer needs at least two modules")
    if len(targets) < 1:
        raise ValueError("composer needs at least one target flow")
    if len(modules) != len(targets):
        raise ValueError(
            f"len(modules)={len(modules)} != len(targets)={len(targets)}: "
            "every module/target flow must be accounted for, none may be dropped"
        )
    if len(gate_inputs) not in (len(modules) - 1, len(modules)):
        raise ValueError(
            f"len(gate_inputs)={len(gate_inputs)} must be len(modules)-1 "
            f"({len(modules) - 1}) or len(modules) ({len(modules)})"
        )
    if len(gate_inputs) == len(modules):
        extra_gate = np.asarray(gate_inputs[-1], dtype=float)
        if not np.all(np.isfinite(extra_gate)):
            raise ValueError("non-finite gate input")

    composite = np.asarray(modules[0], dtype=float)
    penalties = 0.0
    for i in range(len(modules) - 1):
        composite, penalty = compose(composite, modules[i + 1], gate_inputs[i], w, b)
        penalties += penalty
    n_gates = len(modules) - 1

    target_arrays = [np.asarray(t, dtype=float) for t in targets]
    # Compute over ALL flows: one error per target, including the last.
    errors = [float(np.mean((composite - t) ** 2)) for t in target_arrays]
    if len(errors) != len(target_arrays):
        raise ValueError("prediction/target length mismatch")
    # Best single module: worst-case error over ALL flows, minimised over modules.
    single_worsts = [
        max(float(np.mean((np.asarray(m, dtype=float) - t) ** 2)) for t in target_arrays)
        for m in modules
    ]
    best_single_worst = min(single_worsts)
    worst_error = max(errors)

    if n_nodes is not None:
        base = description_length(n_nodes, list(constants or []))
        composite_dl = description_length(
            n_nodes, list(constants or []), n_gates=n_gates
        )
    else:
        base = float(base_dl)
        composite_dl = base + penalties

    return {
        "worst_error": worst_error,
        "best_single_worst": best_single_worst,
        "dl_penalty_bits": penalties,
        "beats_single": worst_error < best_single_worst,
        "n_gates": n_gates,
        "per_flow_errors": errors,
        "single_worst_errors": single_worsts,
        "composite": composite,
        "base_dl": base,
        "composite_dl": composite_dl,
        "dl": composite_dl,
        "total_dl": composite_dl,
        "effective_dl": composite_dl,
    }
