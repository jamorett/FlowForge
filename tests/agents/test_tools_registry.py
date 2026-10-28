"""Test all 11 agent tools registered in flowforge.agents.tools.registry."""
from pathlib import Path
import pytest
from flowforge.agents.tools.registry import TOOLS

REQUIRED_TOOLS = [
    "read_findings",
    "read_scores",
    "search_cards",
    "fit_constants",
    "eval_apriori",
    "render_error_map",
    "sam_segment",
    "request_test",
    "generate_flow",
    "run_attack",
    "fit_gates",
]


def test_all_11_tools_registered() -> None:
    for tool_name in REQUIRED_TOOLS:
        assert tool_name in TOOLS, f"Missing tool: {tool_name}"


def test_eval_apriori_tool() -> None:
    eval_fn = TOOLS["eval_apriori"]
    score = eval_fn("0", case_id="periodic_hill_re5600")
    assert isinstance(score, float)
    assert score > 0.0


def test_fit_constants_tool() -> None:
    fit_fn = TOOLS["fit_constants"]
    res = fit_fn("I1", case_id="periodic_hill_re5600")
    assert "snapped_scale" in res
    assert "apriori_mse" in res


def test_render_and_segment_tools(tmp_path: Path) -> None:
    render_fn = TOOLS["render_error_map"]
    seg_fn = TOOLS["sam_segment"]
    out_png = tmp_path / "test_err.png"
    rendered = render_fn("I1", case_id="periodic_hill_re5600", out_png=str(out_png))
    assert Path(rendered).exists()
    assert Path(rendered).with_suffix(".npy").exists()

    segments = seg_fn(rendered)
    assert isinstance(segments, list)
    assert len(segments) > 0
    assert "box" in segments[0]


def test_skeptic_request_test_tool() -> None:
    req_fn = TOOLS["request_test"]
    res = req_fn("I1", "Unphysical in boundary layer", "curved_step")
    assert res["status"] == "recorded"
    assert res["requested_case"] == "curved_step"


def test_redteam_tools() -> None:
    gen_fn = TOOLS["generate_flow"]
    attack_fn = TOOLS["run_attack"]
    spec = gen_fn(alpha=1.2, reynolds=10595)
    assert spec["alpha"] == 1.2
    assert spec["split"] == "validation"

    attack_res = attack_fn("I1", spec, validation_case="curved_step")
    assert "broken" in attack_res
    assert "candidate_mse" in attack_res


def test_composer_fit_gates_tool() -> None:
    gate_fn = TOOLS["fit_gates"]
    res = gate_fn("0", "I1", case_id="periodic_hill_re5600")
    assert "w" in res
    assert "b" in res
    assert res["dl_penalty_bits"] == 16.0
