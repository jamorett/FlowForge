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
# USD per 1M tokens (input, output), Meta Model API pay-as-you-go.
# Reasoning tokens are billed as output and arrive inside
# completion_tokens. Models without a published price (contributor tier,
# muse-wonder) bill every token at the highest known output rate, so the
# meter over- rather than under-estimates.
PRICE_PER_M = {"muse-spark-1.1": (1.25, 4.25), "muse-spark-1.2": (1.25, 4.25),
               "muse-spark-1.3": (1.25, 4.25)}
FALLBACK_PRICE_PER_M = (max(p[1] for p in PRICE_PER_M.values()),) * 2

T = TypeVar("T", bound=BaseModel)


def cost_for(model: str, completion_tokens: int, prompt_tokens: int = 0) -> float:
    assert completion_tokens >= 0 and prompt_tokens >= 0, "tokens must be >= 0"
    price_in, price_out = PRICE_PER_M.get(model, FALLBACK_PRICE_PER_M)
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000


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

    def complete(self, model: str, prompt: str, max_tokens: int = 2048,
                 temperature: float | None = None,
                 reasoning_effort: str | None = None) -> str:
        assert model and prompt, "model and prompt are required"
        if _replay_enabled():
            return self._complete_replay(model, prompt)
        return self._complete_live(model, prompt, max_tokens, temperature, reasoning_effort)

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
    def _complete_live(self, model: str, prompt: str, max_tokens: int = 2048,
                       temperature: float | None = None,
                       reasoning_effort: str | None = None) -> str:
        self.check_budget(0.01)
        client = self._get_client()
        # Only send what is configured; omitted keys keep the API defaults.
        extra: dict = {}
        if temperature is not None:
            extra["temperature"] = temperature
        if reasoning_effort is not None:
            extra["reasoning_effort"] = reasoning_effort
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            **extra,
        )
        u = resp.usage
        usage = u.total_tokens if u else 0
        prompt_tokens = getattr(u, "prompt_tokens", None)
        completion_tokens = getattr(u, "completion_tokens", None)
        if prompt_tokens is None or completion_tokens is None:
            # No split reported: bill everything at the output rate.
            prompt_tokens, completion_tokens = 0, usage
        self.tokens += usage
        self.spent += cost_for(model, completion_tokens, prompt_tokens)
        text = resp.choices[0].message.content or ""
        self._log_event(prompt, model, usage, text)
        if self.spent > SESSION_LIMIT:
            raise BudgetExceededError(f"Session limit ${SESSION_LIMIT} exceeded (${self.spent:.2f} spent)")
        return text

    def complete_structured(self, model: str, prompt: str, schema: type[T],
                            max_tokens: int = 2048,
                            temperature: float | None = None,
                            reasoning_effort: str | None = None) -> T:
        """Complete, parse JSON, validate with Pydantic. One repair retry, then drop."""
        gen = {"temperature": temperature, "reasoning_effort": reasoning_effort}
        text = self.complete(model, prompt, max_tokens=max_tokens, **gen)
        try:
            return schema.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as first_exc:
            repair_prompt = (
                f"{prompt}\n\nYour previous output failed validation: {first_exc}. "
                f"Return ONLY valid JSON matching the {schema.__name__} schema, "
                "including a non-empty risk_audit field."
            )
            repaired = self.complete(model, repair_prompt, max_tokens=max_tokens, **gen)
            try:
                return schema.model_validate(json.loads(repaired))
            except (json.JSONDecodeError, ValidationError) as second_exc:
                raise ModelValidationError(
                    f"{schema.__name__} validation failed after one repair retry: {second_exc}"
                ) from second_exc
