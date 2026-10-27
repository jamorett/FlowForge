import numpy as np
import pytest

from flowforge.data.ingest import validate_anisotropy
from flowforge.redteam.attacks import broke_threshold, record_attack
from flowforge.render.error_map import error_field, render_png


def test_render_writes_real_png(tmp_path) -> None:
    errs = error_field(np.ones((4, 4, 3)), np.zeros((4, 4, 3)))
    out = render_png(errs, tmp_path / "err.png")
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_record_attack_only_when_broke(tmp_path) -> None:
    assert record_attack({"split": "validation"}, "abcdef123456", False, tmp_path) is None
    path = record_attack({"split": "validation"}, "abcdef123456", True, tmp_path)
    assert path is not None and path.exists()


def test_record_attack_refuses_train(tmp_path) -> None:
    with pytest.raises(AssertionError):
        record_attack({"split": "train"}, "abcdef123456", True, tmp_path)


def test_broke_threshold() -> None:
    assert broke_threshold({"f": 3.0}, {"f": 1.0})
    assert not broke_threshold({"f": 1.2}, {"f": 1.0})


def test_validate_anisotropy_rejects_trace() -> None:
    with pytest.raises(AssertionError):
        validate_anisotropy(np.eye(3)[None])
