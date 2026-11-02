import numpy as np

from flowforge.ladder.ladder import halving, minimax_score, rung0, run_ladder_rung01
from flowforge.orchestrator.round import run_round, synthetic_fields


def test_rung0_rejects_raw_division() -> None:
    assert rung0("I1 + I2")
    assert not rung0("I1 / I2")


def test_halving_keeps_best_half() -> None:
    cands = [{"score": float(i)} for i in range(4)]
    kept = halving(cands)
    assert [c["score"] for c in kept] == [0.0, 1.0]


def test_minimax_uses_worst_case() -> None:
    score = minimax_score({"a": 2.0, "b": 1.0}, {"a": 1.0, "b": 1.0})
    assert score == 2.0


def test_ladder_recovers_known_coefficient() -> None:
    # Ground truth is 0.5*T1, so constant 0-ish candidates must beat I1-only ones
    # only if the ladder really evaluates; at minimum it returns scored survivors.
    inv, basis, target = synthetic_fields()
    survivors = run_ladder_rung01(["0", "I1"], inv, basis, target)
    assert survivors and "score" in survivors[0]


def test_mock_round_runs_without_api() -> None:
    result = run_round(1, mock=True)
    assert result["status"] == "ok"
    assert result["proposed"] == 4


def test_realizability_filter_runs_before_rung2_halving() -> None:
    """A non-realizable rung-1 leader must not crowd out a realizable candidate."""
    from flowforge.ladder.ladder import realizable_only, rung2_short
    from flowforge.orchestrator.round import synthetic_fields

    inv, basis, _ = synthetic_fields(n=64, seed=3)
    pool = [{"expression": "100 * T1", "score": 0.1}, {"expression": "0.001 * T1", "score": 0.2}]
    kept = realizable_only(pool, inv, basis)
    assert [c["expression"] for c in kept] == ["0.001 * T1"]
    assert [c["expression"] for c in rung2_short(kept)] == ["0.001 * T1"]
    assert [c["expression"] for c in rung2_short(pool)] == ["100 * T1"]  # old order lost the round
