from flowforge.agents.runtime.client import cost_for
from flowforge.orchestrator.round import run_round


def test_mock_round_picks_champion() -> None:
    result = run_round(1, mock=True)
    assert result["champion"] is not None
    assert result["champion"]["expression"] in ("0", "I1", "tanh(I1)", "I1 + I2")
    assert result["champion"]["dl"] > 0


def test_cost_for_known_and_unknown_models() -> None:
    assert cost_for("muse-spark-1.3", 1000) == 0.002
    # Unknown models bill at the max known rate, never silently free.
    assert cost_for("unknown-model", 1000) == 0.003
