"""Exact one-sided p-value tests (no API, no data/processed)."""
from __future__ import annotations

import json
import math


def test_separated_groups_u9_p_min() -> None:
    from scripts import run_arms

    first = [0.5, 0.6, 0.7]
    second = [0.8, 0.9, 1.0]
    stat = run_arms.mann_whitney_u(first, second)
    assert stat == 9.0
    p_value = run_arms.mann_whitney_exact_p(first, second)
    assert p_value == 0.05
    assert p_value == 1.0 / float(math.comb(6, 3))


def test_reversed_groups_p_one() -> None:
    from scripts import run_arms

    first = [0.8, 0.9, 1.0]
    second = [0.5, 0.6, 0.7]
    p_value = run_arms.mann_whitney_exact_p(first, second)
    assert p_value == 1.0


def test_identical_samples_p_mid() -> None:
    from scripts import run_arms

    first = [0.5, 0.6, 0.7]
    second = [0.5, 0.6, 0.7]
    p_value = run_arms.mann_whitney_exact_p(first, second)
    assert 0.5 <= p_value <= 1.0


def test_comparisons_in_dry_run(tmp_path, monkeypatch) -> None:
    from flowforge.baselines import sparse as sparse_module
    from flowforge.orchestrator import round as round_module
    from scripts import run_arms

    def fake_run_round(round_no, mock=False, groups=1, session=None, redteam=True, **kwargs):
        assert mock is False
        champion = {"expression": "I1", "worst_validation_ratio": 0.4}
        return {"status": "ok", "champion": champion, "dollars_spent": 0.5, "round": int(round_no)}

    def fake_baseline(seed=42, **kwargs):
        return {"expression": "I1", "worst_validation_ratio": 0.9}

    monkeypatch.setattr(round_module, "run_round", fake_run_round)
    monkeypatch.setattr(sparse_module, "evaluate_sparse_baseline", fake_baseline)

    out_path = tmp_path / "arms.json"
    output = run_arms.main([
        "--dry-run", "--rounds", "1", "--groups", "1",
        "--budget-usd", "100.0", "--out", str(out_path),
    ])
    assert output is not None
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    comparisons = payload.get("comparisons")
    assert isinstance(comparisons, dict)
    rp1 = comparisons.get("swarm_vs_swarm_no_redteam")
    rp2 = comparisons.get("swarm_vs_sparse_baseline")
    assert isinstance(rp1, dict)
    assert isinstance(rp2, dict)
    for entry in (rp1, rp2):
        assert entry.get("available") is True
        assert entry.get("metric") == "worst_validation_ratio"
        assert "u" in entry
        assert "p_one_sided" in entry
        assert "p_min" in entry
        assert entry["p_min"] == 0.05
        assert entry["n1"] == 3
        assert entry["n2"] == 3
    assert rp1["u"] == 4.5
    assert rp1["p_one_sided"] == 1.0
    assert rp2["u"] == 9.0
    assert rp2["p_one_sided"] == 0.05
    assert output["comparisons"] == comparisons
