import numpy as np
import pytest

from flowforge.composer.evaluate import evaluate_composition
from flowforge.literature.harvester import extract_cards
from flowforge.solver.field_io import field_hash, write_correction_fields


def test_write_correction_rejects_asymmetric(tmp_path) -> None:
    bad = np.ones((2, 3, 3))
    bad[0, 0, 1] = 2.0  # Asymmetric: bad[0, 0, 1] != bad[0, 1, 0]
    with pytest.raises(AssertionError):
        write_correction_fields(tmp_path, bad, np.zeros(2))



def test_field_hash_stable() -> None:
    fields = {"U": np.zeros((2, 3))}
    assert field_hash(fields) == field_hash({"U": np.zeros((2, 3))})


def test_extract_cards_rejects_unparseable() -> None:
    text = "MECHANISM: curvature\nFORM: I1 + tanh(I2)\n---\nMECHANISM: x\nFORM: I1 / I2\n"
    cards = extract_cards(text)
    assert len(cards) == 1
    assert cards[0].mechanism == "curvature"


def test_composer_pays_gate_penalty() -> None:
    mods = [np.zeros((2, 3, 3)), np.zeros((2, 3, 3)), np.zeros((2, 3, 3))]
    gates = [np.zeros(2), np.zeros(2), np.zeros(2)]
    tgts = [np.zeros((2, 3, 3)) for _ in range(3)]
    result = evaluate_composition(mods, gates, tgts, w=1.0, b=0.0)
    assert result["dl_penalty_bits"] > 0
    assert result["n_gates"] == 2
