import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from flowforge.agents.runtime.client import (
    SESSION_LIMIT,
    BudgetExceededError,
    ModelRuntime,
    ModelValidationError,
    cost_for,
)
from flowforge.agents.runtime.event_logger import EventLogger, prompt_hash
from flowforge.agents.schemas import ROLE_SCHEMAS, RoundPlan


def test_budget_limit_enforced() -> None:
    rt = ModelRuntime()
    rt.spent = 49.99
    with pytest.raises(BudgetExceededError):
        rt.check_budget(0.02)


def test_event_log_roundtrip(tmp_path) -> None:
    logger = EventLogger(tmp_path)
    logger.log({"prompt_hash": prompt_hash("hi"), "response": {"text": "ok"}})
    assert (tmp_path / "events.jsonl").exists()


def test_session_limit_is_50() -> None:
    assert SESSION_LIMIT == 50.00


def test_event_logger_for_session_path(tmp_path) -> None:
    logger = EventLogger.for_session("s1", runs_root=tmp_path)
    assert logger.path == tmp_path / "s1" / "events.jsonl"


def test_log_response_without_hash_is_error(tmp_path) -> None:
    logger = EventLogger(tmp_path)
    with pytest.raises(ValueError, match="prompt_hash"):
        logger.log({"response": {"text": "x"}})


def test_replay_zero_token(tmp_path, monkeypatch) -> None:
    logger = EventLogger(tmp_path)
    payload = json.dumps({"mechanisms": ["a"], "budget_split": {"board": 1.0}, "risk_audit": "r"})
    logger.log({"prompt_hash": prompt_hash("p"), "model": "m", "tokens": 9, "response": {"text": payload}})
    monkeypatch.setenv("FLOWFORGE_REPLAY", "1")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    rt = ModelRuntime(logger=logger)
    assert rt.complete("muse-spark-1.3", "p") == payload
    assert rt.spent == 0.0 and rt.tokens == 0


def test_replay_miss_and_missing_hash_are_errors(tmp_path, monkeypatch) -> None:
    logger = EventLogger(tmp_path)
    logger.log({"prompt_hash": prompt_hash("p"), "response": {"text": "ok"}})
    monkeypatch.setenv("FLOWFORGE_REPLAY", "1")
    with pytest.raises(RuntimeError, match="Replay miss"):
        ModelRuntime(logger=logger).complete("m", "unrecorded")
    with pytest.raises(RuntimeError, match="missing/empty"):
        logger.replay_lookup("")
    logger.log({"prompt_hash": prompt_hash("q"), "response": {"text": "ok"}})
    (tmp_path / "events.jsonl").write_text(
        (tmp_path / "events.jsonl").read_text() + json.dumps({"response": {"text": "x"}}) + "\n"
    )
    with pytest.raises(RuntimeError, match="missing prompt_hash"):
        logger.replay_lookup(prompt_hash("q"))


class _FakeClient:
    def __init__(self, texts: list[str]):
        self._texts = list(texts)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_kw):
        text = self._texts.pop(0)
        return SimpleNamespace(
            usage=SimpleNamespace(total_tokens=100),
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        )


def _runtime_with_fake(texts: list[str], tmp_path) -> ModelRuntime:
    rt = ModelRuntime(logger=EventLogger(tmp_path))
    rt._client = _FakeClient(texts)  # noqa: SLF001 - test stub, no network
    return rt


def test_structured_validation_and_key_never_logged(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", "sk-test-secret-value")
    good = json.dumps({"mechanisms": ["a"], "budget_split": {"board": 0.5}, "risk_audit": "r"})
    rt = _runtime_with_fake([good], tmp_path)
    out = rt.complete_structured("muse-spark-1.3", "plan?", RoundPlan)
    assert out.mechanisms == ["a"]
    logged = (tmp_path / "events.jsonl").read_text()
    assert "sk-test-secret-value" not in logged
    assert cost_for("muse-spark-1.3", 100) > 0


def test_structured_one_repair_retry_then_drop(tmp_path) -> None:
    bad = json.dumps({"mechanisms": ["a"], "budget_split": {"board": 0.5}})  # no risk_audit
    good = json.dumps({"mechanisms": ["a"], "budget_split": {"board": 0.5}, "risk_audit": "r"})
    rt = _runtime_with_fake([bad, good], tmp_path)
    assert rt.complete_structured("muse-spark-1.3", "plan?", RoundPlan).risk_audit == "r"
    rt2 = _runtime_with_fake([bad, bad], tmp_path / "second")
    with pytest.raises(ModelValidationError):
        rt2.complete_structured("muse-spark-1.3", "plan?", RoundPlan)


def test_all_role_schemas_require_risk_audit() -> None:
    valid = {
        "board": {"mechanisms": ["a"], "budget_split": {"b": 1.0}},
        "theorist": {"expressions": ["0"], "mechanisms": ["m"]},
        "coder": {"constants": [1.0], "apriori_mse": 0.1},
        "analyst": {"failure_regions": ["x"], "next_hypothesis": "h"},
        "skeptic": {"objections": ["o"], "requested_tests": []},
        "redteam": {"flows": [{"name": "hill"}]},
        "composer": {"modules": ["m"], "gates": []},
    }
    for role, base in valid.items():
        schema = ROLE_SCHEMAS[role]
        with pytest.raises(Exception):
            schema.model_validate(dict(base))  # missing risk_audit
        with pytest.raises(Exception):
            schema.model_validate({**base, "risk_audit": "  "})  # blank risk_audit
        assert schema.model_validate({**base, "risk_audit": "ok"}).risk_audit == "ok"


def test_prompt_files_match_schemas() -> None:
    root = Path(__file__).resolve().parents[2] / "prompts"
    for role, schema in ROLE_SCHEMAS.items():
        data = yaml.safe_load((root / f"{role}.yaml").read_text())
        assert data["role"] == role
        assert data["schema"] == schema.__name__
        assert data["risk_audit"] == "required"
        assert "risk_audit" in data["prompt"]
