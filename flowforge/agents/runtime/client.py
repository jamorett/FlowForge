"""Meta Model API client (S4.3). OpenAI SDK -> https://api.meta.ai/v1.

All calls go through ModelRuntime: budget meter, retries, event trace.
Direct client.chat.completions.create outside this module is forbidden.
Key read from MODEL_API_KEY env var; value is never logged.
Replay (FLOWFORGE_REPLAY=1) is zero-token: recorded responses only,
any miss is an error and the network is never touched.
"""

from __future__ import annotations

import json
import os
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

SESSION_LIMIT = 50.00
BASE_URL = "https://api.meta.ai/v1"
# USD per 1K tokens (input+output blended). Update from Meta pricing at
# kickoff; the meter must never run on an invented rate silently, so an
# unknown model falls back to the most expensive known rate.
RATE_PER_1K = {"muse-spark-1.3": 0.002, "muse-code": 0.003, "wonder": 0.002}
FALLBACK_RATE_PER_1K = max(RATE_PER_1K.values())

T = TypeVar("T", bound=BaseModel)


def cost_for(model: str, tokens: int) -> float:
    assert tokens >= 0, "tokens must be >= 0"
    return tokens / 1000.0 * RATE_PER_1K.get(model, FALLBACK_RATE_PER_1K)


class BudgetExceededError(RuntimeError):
    pass


class ModelValidationError(RuntimeError):
    """Structured output failed Pydantic validation after one repair retry."""


def _replay_enabled() -> bool:
    return os.environ.get("FLOWFORGE_REPLAY") == "1"


class ModelRuntime:
    def __init__(self, logger=None):
        self.spent = 0.0
        self.tokens = 0
        self.logger = logger
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            key = os.environ.get("MODEL_API_KEY")
            if not key:
                raise RuntimeError("MODEL_API_KEY is not set")
            # Never log `key`; only its presence is ever recorded.
            self._client = OpenAI(base_url=BASE_URL, api_key=key)
        return self._client

    def check_budget(self, est_dollars: float) -> None:
        assert est_dollars >= 0, "estimate must be >= 0"
        if self.spent + est_dollars > SESSION_LIMIT:
            raise BudgetExceededError(f"Session limit ${SESSION_LIMIT} would be exceeded")

    def _log_event(self, prompt: str, model: str, tokens: int, text: str, schema: str | None = None) -> None:
        if self.logger is None:
            return
        from flowforge.agents.runtime.event_logger import prompt_hash

        event: dict = {"prompt_hash": prompt_hash(prompt), "model": model,
                       "tokens": tokens, "response": {"text": text}}
        if schema is not None:
            event["schema"] = schema
        key = os.environ.get("MODEL_API_KEY") or ""
        assert not key or key not in json.dumps(event), "API key must never be logged"
        self.logger.log(event)

    def complete(self, model: str, prompt: str, max_tokens: int = 2048) -> str:
        assert model and prompt, "model and prompt are required"
        if _replay_enabled():
            return self._complete_replay(model, prompt)
        return self._complete_live(model, prompt, max_tokens)

    def _complete_replay(self, model: str, prompt: str) -> str:
        if self.logger is None:
            raise RuntimeError("Replay mode requires an EventLogger; live calls are forbidden")
        from flowforge.agents.runtime.event_logger import prompt_hash

        spent_before, tokens_before = self.spent, self.tokens
        resp = self.logger.replay_lookup(prompt_hash(prompt))
        assert resp is not None, "replay_lookup must return a response in replay mode"
        text = resp.get("text")
        if not isinstance(text, str):
            raise RuntimeError("Recorded response has no text; cannot replay")
        assert self.spent == spent_before and self.tokens == tokens_before, "replay must be zero-token"
        return text

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=8),
           reraise=True)
    def _complete_live(self, model: str, prompt: str, max_tokens: int = 2048) -> str:
        self.check_budget(0.01)
        client = self._get_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        usage = resp.usage.total_tokens if resp.usage else 0
        self.tokens += usage
        self.spent += cost_for(model, usage)
        text = resp.choices[0].message.content or ""
        self._log_event(prompt, model, usage, text)
        if self.spent > SESSION_LIMIT:
            raise BudgetExceededError(f"Session limit ${SESSION_LIMIT} exceeded (${self.spent:.2f} spent)")
        return text

    def complete_structured(self, model: str, prompt: str, schema: type[T],
                            max_tokens: int = 2048) -> T:
        """Complete, parse JSON, validate with Pydantic. One repair retry, then drop."""
        text = self.complete(model, prompt, max_tokens=max_tokens)
        try:
            return schema.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as first_exc:
            repair_prompt = (
                f"{prompt}\n\nYour previous output failed validation: {first_exc}. "
                f"Return ONLY valid JSON matching the {schema.__name__} schema, "
                "including a non-empty risk_audit field."
            )
            repaired = self.complete(model, repair_prompt, max_tokens=max_tokens)
            try:
                return schema.model_validate(json.loads(repaired))
            except (json.JSONDecodeError, ValidationError) as second_exc:
                raise ModelValidationError(
                    f"{schema.__name__} validation failed after one repair retry: {second_exc}"
                ) from second_exc
