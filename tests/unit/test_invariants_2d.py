"""2-D invariant guard: I3..I5 carry no independent information."""
from __future__ import annotations

import pytest

from flowforge.baselines.sparse import _FEATURE_NAMES
from flowforge.dsl.parser import validate_candidate


@pytest.mark.parametrize(
    ("text", "symbol"),
    [
        ("I3 * T1", "I3"),
        ("div(1, I4) * T2", "I4"),
        ("0.1 * I5", "I5"),
    ],
)
def test_rejected_invariants_name_symbol(text: str, symbol: str) -> None:
    """I3/I4/I5 are rejected with a message naming the symbol."""
    with pytest.raises(ValueError, match=symbol):
        validate_candidate(text)


def test_allowed_invariants_accepted() -> None:
    """I1/I2-only expressions still validate."""
    validate_candidate("tanh(I1) * T1 + I2 * T2")


def test_sparse_library_has_no_redundant_invariants() -> None:
    """Sparse library shares the DSL symbol set (no I3/I4/I5)."""
    assert "I3" not in _FEATURE_NAMES
    assert "I4" not in _FEATURE_NAMES
    assert "I5" not in _FEATURE_NAMES
