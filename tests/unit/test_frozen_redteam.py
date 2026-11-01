"""Frozen-mode red team (RP1) unit tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _setup(monkeypatch, tmp_path):
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields
    from flowforge.ladder import ladder as ladder_mod
    from flowforge.orchestrator import round as round_mod
    from flowforge.orchestrator.round import synthetic_fields
    inv0, basis0, target0 = synthetic_fields(n=8, seed=123)
    monkeypatch.setattr(round_mod, "ATTACKS_DIR", tmp_path / "attacks")
    monkeypatch.setattr(frozen_fields, "train_case_ids", lambda root=None: ["train_stub"])
    monkeypatch.setattr(frozen_fields, "validation_case_ids", lambda root=None: ["val_stub"])
    monkeypatch.setattr(frozen_fields, "redteam_case_ids", lambda root=None: ["rt_stub"])
    monkeypatch.setattr(frozen_fields, "load_frozen_fields", lambda c, processed_dir="data/processed", max_points_per_case=None, seed=0: (inv0, basis0, target0))
    avail = [{"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600, "case_id": "attack_a"}]
    monkeypatch.setattr(frozen_fields, "available_attack_flows", lambda processed_dir="data/processed": [dict(avail[0])])
    def fake_case_for(flow, processed_dir="data/processed"):
        if isinstance(flow, dict) and str(flow.get("kind", "")).lower() == "periodic_hill" and abs(float(flow.get("alpha", 9e9)) - 0.5) < 0.06:
            return "attack_a"
        return None
    monkeypatch.setattr(frozen_fields, "attack_case_for", fake_case_for)
    calls = {"attack": 0}
    def fake_score(expr, case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        out = {}
        for cid in list(case_ids):
            if cid == "attack_a":
                calls["attack"] += 1
                ratio = 2.0 if "I1" in str(expr) else 0.5
                out[cid] = {"mse": ratio, "mse_zero": 1.0, "ratio": ratio, "n_used": 1, "n_excluded": 0}
            else:
                out[cid] = {"mse": 0.5, "mse_zero": 1.0, "ratio": 0.5, "n_used": 1, "n_excluded": 0}
        return out
    monkeypatch.setattr(frozen_fields, "score_on_cases", fake_score)
    def fake_ladder(exprs, inv, basis, target, short_eval=None):
        surv = [{"expression": e, "score": 0.0} for e in exprs]
        return {"rung0": surv, "rung0_passed": surv, "rung1": list(surv), "rung2": list(surv), "rung3": list(surv)}
    monkeypatch.setattr(ladder_mod, "run_ladder", fake_ladder)
    seen = {}
    def fake_dispatch(role, runtime, context):
        class Res:
            def __init__(self, payload):
                self.payload = dict(payload)
            def model_dump(self):
                return dict(self.payload)
        if role == "redteam":
            seen["ctx"] = dict(context)
            return Res({"flows": [{"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}, {"kind": "bump", "alpha": 9.0, "reynolds": 100}], "risk_audit": "fake"})
        if role == "theorist":
            # Four proposals so rung-1 halving keeps two fitted survivors:
            # "0.5" and an I1-form that the fake attack breaks off-training.
            return Res({"expressions": ["0", "I1", "2 * T2", "5 * T3"], "mechanisms": ["m"], "risk_audit": "fake"})
        if role == "board":
            return Res({"mechanisms": [], "budget_split": {"theorist": 1.0}, "risk_audit": "fake"})
        if role == "coder":
            return Res({"constants": [], "apriori_mse": 0.0, "risk_audit": "fake"})
        if role == "analyst":
            return Res({"failure_regions": [], "next_hypothesis": "h", "risk_audit": "fake"})
        if role == "skeptic":
            return Res({"objections": [], "requested_tests": [], "risk_audit": "fake"})
        if role == "composer":
            return Res({"modules": ["0"], "gates": [], "risk_audit": "fake"})
        return Res({"risk_audit": "fake"})
    monkeypatch.setattr(dispatcher, "dispatch_role", fake_dispatch)
    return seen, calls


def test_frozen_redteam_breaks_and_persists(tmp_path, monkeypatch):
    from flowforge.orchestrator.round import run_round
    seen, calls = _setup(monkeypatch, tmp_path)
    result = run_round(1, mock=False, session_dir=tmp_path / "sess")
    assert result["status"] == "ok"
    assert calls["attack"] > 0
    assert "available_frozen_flows" in seen["ctx"]
    assert seen["ctx"]["available_frozen_flows"][0]["case_id"] == "attack_a"
    champ = result["champion"]
    assert champ is not None
    assert "I1" not in str(champ["expression"])
    assert champ["attack_ratios"] == {"attack_a": 0.5}
    events = [json.loads(line) for line in Path(result["events_path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    rt = [e for e in events if e.get("type") == "redteam"][-1]
    assert rt["mode"] == "frozen"
    assert rt["pool"] == "rung1"
    assert len(rt["attacks"]) == 2
    assert rt["attacks"][0]["available"] is True and rt["attacks"][0]["case_id"] == "attack_a"
    assert rt["attacks"][1]["available"] is False and rt["attacks"][1]["case_id"] is None
    assert rt["n_broken"] == 1
    assert rt["breaks"][0]["case_id"] == "attack_a" and rt["breaks"][0]["ratio"] == 2.0
    assert "I1" in rt["breaks"][0]["expression"]
    assert rt["breaks"][0]["expression"] in rt["excluded"]
    order = [e.get("type") for e in events]
    assert order.index("redteam") < order.index("rung2")
    assert all(s.get("expression") != rt["breaks"][0]["expression"] for s in result["final_rung3"])
    files = list((tmp_path / "attacks").glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["role"] == "redteam" and payload["mode"] == "frozen" and payload["status"] == "active"
    assert payload["base_case"] == "attack_a" and payload["ratio"] == 2.0
    assert payload["parameter_sweeps"] == {"slope_steepness_alpha": 0.5, "reynolds_number": 5600}
    assert payload["broken_expression"] == rt["breaks"][0]["expression"]
    expect = "attack_" + hashlib.sha256(f"attack_a|{payload['broken_expression']}".encode()).hexdigest()[:10] + ".json"
    assert files[0].name == expect
    assert payload["created_at"].endswith("Z")


def test_redteam_false_is_ablation(tmp_path, monkeypatch):
    from flowforge.orchestrator.round import run_round
    seen, calls = _setup(monkeypatch, tmp_path)
    result = run_round(1, mock=False, session_dir=tmp_path / "sess", redteam=False)
    assert result["status"] == "ok"
    assert calls["attack"] == 0
    assert "ctx" not in seen
    assert not (tmp_path / "attacks").exists() or not list((tmp_path / "attacks").glob("*.json"))
    events = [json.loads(line) for line in Path(result["events_path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    rt = [e for e in events if e.get("type") == "redteam"][-1]
    assert rt.get("skipped") is True
    assert "attack_ratios" not in (result["champion"] or {})
