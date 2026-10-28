"""Regression tests for CH-06 composer fixes (A1).

Plain asserts only: runnable under pytest and directly via
``run_all()`` without pytest fixtures (pytest is absent in some envs).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from flowforge.composer.evaluate import evaluate_composition
from flowforge.composer.gates import compose
from flowforge.elegance.engine import description_length, pick_champion


def _raises_value_error(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def test_mismatched_lengths_raise_value_error() -> None:
    mods = [np.zeros(2), np.zeros(2), np.zeros(2)]
    gates = [np.zeros(2)] * 3
    tgts = [np.zeros(2), np.zeros(2), np.full(2, 99.0)]
    # targets/modules mismatch
    assert _raises_value_error(
        lambda: evaluate_composition(mods, gates, tgts[:2], 1.0, 0.0)
    )
    # gate_inputs mismatch (neither len-1 nor len)
    assert _raises_value_error(
        lambda: evaluate_composition(mods, gates[:1], tgts, 1.0, 0.0)
    )
    assert _raises_value_error(
        lambda: evaluate_composition(mods, gates + gates, tgts, 1.0, 0.0)
    )
    # too few modules / no targets
    assert _raises_value_error(
        lambda: evaluate_composition(mods[:1], gates[:1], tgts[:1], 1.0, 0.0)
    )
    assert _raises_value_error(
        lambda: evaluate_composition(mods, gates, [], 1.0, 0.0)
    )


def test_last_flow_is_scored_regression() -> None:
    # Audit repro: targets [0, 0, 99] previously gave worst_error 0.0, beats_single True.
    mods = [np.zeros(2), np.zeros(2), np.zeros(2)]
    r = evaluate_composition(
        mods, [np.zeros(2)] * 3,
        [np.zeros(2), np.zeros(2), np.full(2, 99.0)], 1.0, 0.0,
    )
    assert r["worst_error"] == 99.0 ** 2
    assert r["per_flow_errors"][-1] == 99.0 ** 2
    assert len(r["per_flow_errors"]) == 3
    assert r["beats_single"] is False


def test_compose_kernel_unchanged() -> None:
    out, pen = compose(np.ones(2), np.zeros(2), np.array([0.0, 1.0]), w=1.0, b=0.0)
    assert abs(float(out[0]) - 0.5) < 1e-12
    assert abs(float(out[1]) - 0.7310585786300049) < 1e-12
    assert pen == 16.0


def test_gate_penalty_wired_into_description_length() -> None:
    ungated = description_length(5, [0.5])
    assert description_length(5, [0.5], n_gates=1) >= ungated + 16.0
    assert description_length(5, [0.5], n_gates=1) == ungated + 16.0
    assert description_length(5, [0.5], n_gates=2) == ungated + 32.0
    assert description_length(5, [0.5], dl_penalty_bits=16.0) == ungated + 16.0
    assert description_length(5, [0.5], gate_penalty_bits=16.0) == ungated + 16.0
    # Backward compatible default.
    assert description_length(5, [0.5]) == ungated


def test_pick_champion_charges_gate_penalty() -> None:
    base = description_length(5, [0.5])
    ungated = {"id": "ungated", "worst_error": 1.0, "dl": base}
    gated_bits = {"id": "gated", "worst_error": 1.0, "dl": base, "dl_penalty_bits": 16.0}
    gated_n = {"id": "gated_n", "worst_error": 1.0, "dl": base, "n_gates": 1}
    gated_dl = {
        "id": "gated_dl", "worst_error": 1.0,
        "dl": description_length(5, [0.5], n_gates=1),
    }
    assert pick_champion([gated_bits, ungated])["id"] == "ungated"
    assert pick_champion([gated_n, ungated])["id"] == "ungated"
    assert pick_champion([gated_dl, ungated])["id"] == "ungated"
    # A clearly better gated candidate still wins outside the 3% pool.
    better = {"id": "better", "worst_error": 0.5, "dl": base, "n_gates": 1}
    assert pick_champion([better, ungated])["id"] == "better"
    # Pre-existing behaviour without any gate fields is unchanged.
    assert pick_champion([
        {"id": "a", "worst_error": 1.0, "dl": 10.0},
        {"id": "b", "worst_error": 1.02, "dl": 50.0},
    ])["id"] == "a"


def test_evaluate_composite_dl_includes_penalty() -> None:
    mods = [np.zeros((2, 3, 3)) for _ in range(3)]
    gates = [np.zeros(2) for _ in range(3)]
    tgts = [np.zeros((2, 3, 3)) for _ in range(3)]
    r = evaluate_composition(mods, gates, tgts, w=1.0, b=0.0)
    assert r["n_gates"] == 2
    assert r["dl_penalty_bits"] == 32.0
    # Default base_dl=0: composite DL is exactly the gate penalty.
    assert r["composite_dl"] == 32.0
    assert r["dl"] == r["composite_dl"]
    r2 = evaluate_composition(mods, gates, tgts, w=1.0, b=0.0, base_dl=100.0)
    assert r2["composite_dl"] == 132.0
    assert r2["composite_dl"] > 100.0 + 16.0
    r3 = evaluate_composition(mods, gates, tgts, w=1.0, b=0.0, n_nodes=5, constants=[0.5])
    assert r3["composite_dl"] == description_length(5, [0.5], n_gates=2)
    assert r3["composite_dl"] >= description_length(5, [0.5]) + 32.0
    # Champion comparison: gated composite pays >=16 bits vs same-base ungated.
    champ = pick_champion([
        {"id": "ungated", "worst_error": 1.0, "dl": 100.0},
        {"id": "gated", "worst_error": 1.0, "dl": r2["composite_dl"]},
    ])
    assert champ["id"] == "ungated"


def test_evaluate_beats_single_only_when_composite_wins_all_flows() -> None:
    # Sequential blend of [1, 0, 0] at gate 0.5 twice -> 0.25 on every flow.
    mods = [np.ones(2), np.zeros(2), np.zeros(2)]
    tgts = [np.full(2, 0.25) for _ in range(3)]
    r = evaluate_composition(mods, [np.zeros(2)] * 3, tgts, 1.0, 0.0)
    assert r["worst_error"] == 0.0
    assert r["beats_single"] is True
    # Same composite cannot beat a single when the last flow disagrees.
    tgts_bad = [np.full(2, 0.25), np.full(2, 0.25), np.full(2, 99.0)]
    r_bad = evaluate_composition(mods, [np.zeros(2)] * 3, tgts_bad, 1.0, 0.0)
    assert r_bad["worst_error"] > 1000.0
    assert r_bad["beats_single"] is False


def run_all() -> None:
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL_PASS")


if __name__ == "__main__":
    run_all()
