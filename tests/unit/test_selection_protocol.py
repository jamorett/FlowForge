"""Selection protocol: champion must not use validation (Task 14)."""
from __future__ import annotations

import json
from pathlib import Path


def _install_fakes(monkeypatch, tmp_path):
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields
    from flowforge.dsl import expr_fit as expr_fit_mod
    from flowforge.ladder import ladder as ladder_mod
    from flowforge.orchestrator import round as round_mod
    from flowforge.orchestrator.round import synthetic_fields

    inv0, basis0, target0 = synthetic_fields(n=8, seed=123)
    monkeypatch.setattr(round_mod, "ATTACKS_DIR", tmp_path / "attacks")
    monkeypatch.setattr(frozen_fields, "train_case_ids", lambda root=None: ["train_stub"])
    monkeypatch.setattr(frozen_fields, "validation_case_ids", lambda root=None: ["val_stub"])

    def fake_load(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0, return_b_rans=False):
        if return_b_rans:
            return (inv0, basis0, target0, None)
        return (inv0, basis0, target0)

    monkeypatch.setattr(frozen_fields, "load_frozen_fields", fake_load)
    avail = [{"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600, "case_id": "attack_a"}]
    monkeypatch.setattr(frozen_fields, "available_attack_flows", lambda processed_dir="data/processed": [dict(avail[0])])

    def fake_case_for(flow, processed_dir="data/processed"):
        if isinstance(flow, dict) and str(flow.get("kind", "")).lower() == "periodic_hill":
            try:
                alpha = float(flow.get("alpha"))
            except (TypeError, ValueError):
                return None
            if abs(alpha - 0.5) < 0.06:
                return "attack_a"
        return None

    monkeypatch.setattr(frozen_fields, "attack_case_for", fake_case_for)

    def fake_score_expr(expression, inv, basis, target):
        text = str(expression)
        ratio = 0.9 if "I1" in text else 0.5
        return {"mse": ratio, "mse_zero": 1.0, "ratio": ratio, "n_used": 8, "n_excluded": 0}

    monkeypatch.setattr(frozen_fields, "score_expression", fake_score_expr)

    def fake_score_cases(expression, case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        text = str(expression)
        out = {}
        for cid in list(case_ids):
            if cid == "attack_a":
                ratio = 0.4
            elif cid == "val_stub":
                ratio = 0.1 if "I1" in text else 0.8
            else:
                ratio = 0.5
            out[cid] = {"mse": ratio, "mse_zero": 1.0, "ratio": ratio, "n_used": 1, "n_excluded": 0}
        return out

    monkeypatch.setattr(frozen_fields, "score_on_cases", fake_score_cases)
    monkeypatch.setattr(ladder_mod, "rung0", lambda expr: True)
    monkeypatch.setattr(ladder_mod, "rung1_scores", lambda exprs, inv, basis, target: [{"expression": e, "score": 0.0} for e in exprs])
    monkeypatch.setattr(ladder_mod, "halving", lambda scores: list(scores))
    monkeypatch.setattr(ladder_mod, "rung2_short", lambda advanced, short_eval=None: list(advanced))
    monkeypatch.setattr(
        ladder_mod, "rung3_full",
        lambda rung2, inv, basis, target, b_rans=None: list(rung2),
    )
    monkeypatch.setattr(expr_fit_mod, "fit_expression",
        lambda expr, inv, basis, target, snap=True, b_rans=None: {"expression": str(expr), "status": "ok",
            "constants": [], "mse_before": 1.0, "mse_after": 0.5, "original": str(expr)})

    def fake_dispatch(role, runtime, context):
        class Res:
            def __init__(self, payload):
                self.payload = dict(payload)
            def model_dump(self):
                return dict(self.payload)
        if role == "theorist":
            return Res({"expressions": ["I1", "0"], "mechanisms": ["m"], "risk_audit": "fake"})
        if role == "board":
            return Res({"mechanisms": [], "budget_split": {"theorist": 1.0}, "risk_audit": "fake"})
        if role == "coder":
            return Res({"constants": [], "apriori_mse": 0.0, "risk_audit": "fake"})
        if role == "redteam":
            return Res({"flows": [{"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}], "risk_audit": "fake"})
        if role == "analyst":
            return Res({"failure_regions": [], "next_hypothesis": "h", "risk_audit": "fake"})
        if role == "skeptic":
            return Res({"objections": [], "requested_tests": [], "risk_audit": "fake"})
        if role == "composer":
            return Res({"modules": ["0"], "gates": [], "risk_audit": "fake"})
        return Res({"risk_audit": "fake"})

    monkeypatch.setattr(dispatcher, "dispatch_role", fake_dispatch)


def _read_events(result):
    return [json.loads(line) for line in Path(result["events_path"]).read_text(encoding="utf-8").splitlines() if line.strip()]


def test_champion_uses_train_not_validation(tmp_path, monkeypatch):
    from flowforge.orchestrator.round import run_round

    _install_fakes(monkeypatch, tmp_path)
    result = run_round(1, mock=False, session_dir=tmp_path / "sess")
    assert result["status"] == "ok"
    champ = result["champion"]
    assert champ is not None
    # A=I1 is better on validation (0.1 vs 0.8) but worse on train (0.9 vs 0.5).
    # Selection must ignore validation, so B=0 wins.
    assert champ["expression"] == "0"
    assert champ["selection_metric"] == "max(train_ratio, attack_ratios)"
    assert champ["selection_ratio"] == 0.5
    # Validation is still computed and reported for the chosen champion.
    assert champ["validation"]["val_stub"]["ratio"] == 0.8
    assert champ["worst_validation_ratio"] == 0.8
    assert champ["attack_ratios"] == {"attack_a": 0.4}
    events = _read_events(result)
    logged = [e for e in events if e.get("type") in ("champion", "composer")]
    assert logged
    assert any(e.get("champion", {}).get("selection_metric") == "max(train_ratio, attack_ratios)" for e in logged)
    assert all(e.get("champion", {}).get("selection_metric") != "worst_validation_ratio" for e in logged if e.get("champion"))


def test_champion_train_alone_when_redteam_off(tmp_path, monkeypatch):
    from flowforge.orchestrator.round import run_round

    _install_fakes(monkeypatch, tmp_path)
    result = run_round(1, mock=False, session_dir=tmp_path / "sess-off", redteam=False)
    assert result["status"] == "ok"
    champ = result["champion"]
    assert champ is not None
    assert champ["expression"] == "0"
    assert champ["selection_metric"] == "max(train_ratio, attack_ratios)"
    assert champ["validation"]["val_stub"]["ratio"] == 0.8
    assert champ["worst_validation_ratio"] == 0.8
    assert "attack_ratios" not in champ
