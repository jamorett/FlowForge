"""Loop v2 wiring on synthetic fields with a fake LLM (no data, no API)."""
import json

import numpy as np
import pytest

from flowforge.agents.schemas import AnalysisReport, CandidateProposal
from flowforge.orchestrator import loop_v2

TRAIN, HELD, VAL = ["train_a", "train_b"], ["held_a"], ["val_stub"]


def _fields(seed, scale=0.05, n=40):
    from flowforge.physics.tensors import invariants, normalized_tensors, tensor_basis

    rng = np.random.default_rng(seed)
    s, w = normalized_tensors(0.2 * rng.standard_normal((n, 3, 3)), np.full(n, 2.0))
    basis = tensor_basis(s, w)
    t1 = basis["T1"]
    target = scale * (t1 - np.trace(t1, axis1=1, axis2=2)[:, None, None] / 3 * np.eye(3))
    return invariants(s, w), basis, target


@pytest.fixture
def fake_world(monkeypatch, tmp_path):
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields

    seeds = {"train_a": 1, "train_b": 2, "held_a": 3, "val_stub": 4}

    def fake_load(case_ids, max_points_per_case=None, return_b_rans=False, **_):
        parts = [_fields(seeds[c]) for c in case_ids]
        inv = {k: np.concatenate([p[0][k] for p in parts]) for k in parts[0][0]}
        basis = {k: np.concatenate([p[1][k] for p in parts]) for k in parts[0][1]}
        target = np.concatenate([p[2] for p in parts])
        return (inv, basis, target, np.zeros_like(target)) if return_b_rans else (inv, basis, target)

    monkeypatch.setattr(frozen_fields, "load_frozen_fields", fake_load)
    monkeypatch.setattr(frozen_fields, "train_case_ids", lambda root=None: list(TRAIN))
    monkeypatch.setattr(frozen_fields, "selection_case_ids", lambda: list(HELD))
    monkeypatch.setattr(frozen_fields, "validation_case_ids", lambda root=None: list(VAL))
    monkeypatch.setattr(loop_v2, "_CASES", {})

    calls: list[tuple[str, dict]] = []
    theorist_fails = {"on": False}

    def fake_dispatch(role, runtime, context=None, **_):
        calls.append((role, json.loads(json.dumps(context, default=str))))
        if role == "diagnostician":
            return AnalysisReport(risk_audit="r", failure_regions=["train_b"], next_hypothesis="h")
        if role == "theorist_v2":
            if theorist_fails["on"]:
                raise dispatcher.RoleDispatchError("schema")
            return CandidateProposal(risk_audit="r", mechanisms=["m"], expressions=[
                "0.1 * T1", "0.1 * T1 + 0.1 * T2", "0.1 * tanh(I1) * T1"])
        if role == "reviser":
            return CandidateProposal(risk_audit="r", mechanisms=["m"], expressions=["0.1 * T1 + 0.1 * T3"])
        raise AssertionError(f"loop v2 must not dispatch {role}")

    monkeypatch.setattr(dispatcher, "dispatch_role", fake_dispatch)
    return {"calls": calls, "dir": tmp_path / "sess", "theorist_fails": theorist_fails}


def test_round_wiring_and_no_validation_leak(fake_world) -> None:
    r1 = loop_v2.run_round(1, session_dir=fake_world["dir"], groups=1)
    assert r1["status"] == "ok" and r1["loop"] == "v2", r1
    champ = r1["champion"]
    assert champ["worst_validation_ratio"] is not None and "val_stub" in champ["validation"]

    roles = [role for role, _ in fake_world["calls"]]
    assert roles == ["diagnostician", "theorist_v2", "reviser"]
    reviser_ctx = fake_world["calls"][2][1]
    assert all("train_cases" in c and "heldout_cases" in c for c in reviser_ctx["your_candidates"])
    assert fake_world["calls"][0][1]["population"] == []  # round 1: nothing yet

    r2 = loop_v2.run_round(2, session_dir=fake_world["dir"], groups=1)
    assert r2["status"] == "ok"
    diag2 = fake_world["calls"][3][1]
    assert diag2["population"], "population must carry into the next round"
    for _, ctx in fake_world["calls"]:  # no LLM context may carry validation
        assert "val_stub" not in json.dumps(ctx) and "validation" not in json.dumps(ctx)

    events = [json.loads(line) for line in (fake_world["dir"] / "events.jsonl").read_text().splitlines()]
    assert [e["type"] for e in events if e["round"] == 1] == list(loop_v2.ROUND_STEPS_V2)
    assert "Infinity" not in (fake_world["dir"] / "events.jsonl").read_text()  # strict JSON for the UI


def test_failed_theorist_injects_no_candidates(fake_world) -> None:
    fake_world["theorist_fails"]["on"] = True
    r = loop_v2.run_round(1, session_dir=fake_world["dir"], groups=1)
    assert r["status"] == "all_rejected" and r["proposed"] == 0
    assert [role for role, _ in fake_world["calls"]] == ["diagnostician", "theorist_v2"]


def _cand(expr, sel, broken=False, nodes=5):
    return {"expression": expr, "status": "ok", "realizable": True, "selection": sel,
            "train_ratio": sel, "broken": broken, "nodes": nodes, "heldout_cases": {}}


def test_population_diversity_and_champion_avoids_broken() -> None:
    new = [_cand(f"{c} * T1", 0.5 + i / 100) for i, c in enumerate((1, 2, 3))]
    new += [_cand("0.2 * T2", 0.9), _cand("0.3 * T1 + 0.1 * T3", 0.4, broken=True),
            {"expression": "bad", "status": "ok", "realizable": False, "selection": 0.1,
             "broken": False, "nodes": 3}]
    pop = loop_v2.update_population([], new, k=5)
    exprs = [p["expression"] for p in pop]
    assert "bad" not in exprs  # non-realizable never enters
    assert "0.2 * T2" in exprs  # diversity cap keeps a second tensor set
    assert pop[-1]["broken"]  # broken ranks last
    assert loop_v2.pick_champion_v2(pop, redteam=True)["expression"] == "1 * T1"
    assert loop_v2.pick_champion_v2([_cand("x * T1", 0.4, broken=True)], redteam=True) is not None


def test_v21_reports_parser_reason_and_node_count(fake_world, monkeypatch) -> None:
    import numpy as np

    inv, basis, target = _fields(1)
    train = (inv, basis, target, np.zeros_like(target))
    over = " + ".join(f"0.1 * tanh(I1 + {i}) * T1" for i in range(6))  # well over 25 nodes
    bad = loop_v2.evaluate(over, train, [], [], 1.0)
    assert bad["status"] == "invalid" and "exceeds cap" in bad["reason"]
    good = loop_v2.evaluate("0.1 * T1", train, [], [], 1.0)
    assert good["nodes"] > 0 and 0.0 <= good["realizable_fraction"] <= 1.0

    from flowforge.agents import dispatcher
    seen = {}
    monkeypatch.setattr(dispatcher, "dispatch_role",
                        lambda role, rt, ctx=None, **kw: seen.update(kw, ctx=ctx) or None)
    loop_v2._dispatch("reviser", None, {"x": 1})
    assert seen["max_tokens"] == loop_v2.MAX_COMPLETION_TOKENS == 50_000 and seen["ctx"]["max_nodes"] == 25
