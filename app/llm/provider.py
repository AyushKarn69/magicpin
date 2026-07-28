"""LLM provider interface, OpenAI implementation, and deterministic fallbacks."""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.utils.logging import get_logger

logger = get_logger(__name__)

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider cannot complete a request."""


@dataclass(frozen=True)
class TokenUsage:
    """Token and cost accounting for one provider call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    def compose(self, prompt: str, cache_key: str | None = None) -> str:
        """Generate a structured JSON response from a prompt."""
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        """Return whether the provider is configured and reachable."""
        raise NotImplementedError

    @abstractmethod
    def retry(self, prompt: str, cache_key: str | None = None) -> str:
        """Retry a provider call according to provider policy."""
        raise NotImplementedError


class FallbackTemplateProvider(LLMProvider):
    """Deterministic category templates used when OpenAI is unavailable."""

    def compose(self, prompt: str, cache_key: str | None = None) -> str:
        requested_cta = self._requested_cta(prompt)
        prompt_lower = prompt.lower()

        if "dentists" in prompt_lower or "peer_clinical" in prompt_lower:
            base = "Quick note: one relevant dental update is ready from the verified facts."
        elif "restaurants" in prompt_lower:
            base = "Quick operational nudge from today's verified trigger."
        elif "salons" in prompt_lower:
            base = "Quick salon update: this trigger is ready for a short customer draft."
        elif "gyms" in prompt_lower:
            base = "Quick fitness update from the supplied context."
        elif "pharmacies" in prompt_lower:
            base = "Quick pharmacy update: this needs a precise customer note."
        else:
            base = "Quick update from Vera."

        if requested_cta == "binary_yes_stop":
            body = f"{base} Reply YES and I will draft it, or STOP to skip."
        elif requested_cta == "none":
            body = base
        else:
            body = f"{base} Want me to draft the next message?"

        return json.dumps(
            {
                "action": "send",
                "body": body,
                "cta": requested_cta,
                "rationale": "Deterministic fallback template used.",
                "wait_seconds": None,
            }
        )

    def health_check(self) -> bool:
        return True

    def retry(self, prompt: str, cache_key: str | None = None) -> str:
        return self.compose(prompt, cache_key=cache_key)

    def _requested_cta(self, prompt: str) -> str:
        try:
            parsed = json.loads(prompt)
            cta = parsed.get("decision_card", {}).get("cta")
            if cta in {"binary_yes_stop", "open_ended", "none"}:
                return str(cta)
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        return "open_ended"


class MockLLMProvider(FallbackTemplateProvider):
    """Backward-compatible test provider alias."""


class OpenAIProvider(LLMProvider):
    """Production OpenAI provider with retries, caching, and cost logging."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        fallback_provider: LLMProvider | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 0.5,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.fallback_provider = fallback_provider or FallbackTemplateProvider()
        self._cache: dict[str, str] = {}
        self.last_usage = TokenUsage()

    def compose(self, prompt: str, cache_key: str | None = None) -> str:
        """Generate JSON output, using cache and fallback on provider failure."""
        resolved_cache_key = cache_key or self._hash_prompt(prompt)
        cached = self._cache.get(resolved_cache_key)
        if cached is not None:
            logger.info("llm_cache_hit", model=self.model_name, cache_key=resolved_cache_key)
            return cached

        if not self.api_key:
            logger.warning("openai_api_key_missing", model=self.model_name)
            response = self.fallback_provider.compose(prompt, cache_key=resolved_cache_key)
            self._cache[resolved_cache_key] = response
            return response

        try:
            response = self.retry(prompt, cache_key=resolved_cache_key)
        except LLMProviderError as exc:
            logger.error("openai_provider_failed", error=str(exc), model=self.model_name)
            response = self.fallback_provider.compose(prompt, cache_key=resolved_cache_key)

        self._cache[resolved_cache_key] = response
        return response

    def health_check(self) -> bool:
        """Check whether OpenAI is configured and reachable."""
        if not self.api_key:
            return False

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    f"https://api.openai.com/v1/models/{self.model_name}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            return response.status_code < 500
        except httpx.HTTPError as exc:
            logger.warning("openai_health_check_failed", error=str(exc))
            return False

    def retry(self, prompt: str, cache_key: str | None = None) -> str:
        """Call OpenAI with exponential backoff."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._call_openai(prompt)
            except (httpx.TimeoutException, httpx.HTTPError, KeyError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "openai_call_retryable_error",
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1,
                    error=str(exc),
                    model=self.model_name,
                )
                if attempt < self.max_retries:
                    time.sleep(self.backoff_base_seconds * (2**attempt))

        raise LLMProviderError(str(last_error) if last_error else "unknown provider error")

    def _call_openai(self, prompt: str) -> str:
        started = time.perf_counter()
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 500,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "vera_action_response",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "action": {"type": "string", "enum": ["send", "wait", "end"]},
                            "body": {"type": ["string", "null"]},
                            "cta": {"type": ["string", "null"]},
                            "rationale": {"type": "string"},
                            "wait_seconds": {"type": ["integer", "null"]},
                        },
                        "required": [
                            "action",
                            "body",
                            "cta",
                            "rationale",
                            "wait_seconds",
                        ],
                    },
                },
            },
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                OPENAI_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        self.last_usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=self._estimate_cost(prompt_tokens, completion_tokens),
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "openai_call_complete",
            model=self.model_name,
            prompt_tokens=self.last_usage.prompt_tokens,
            completion_tokens=self.last_usage.completion_tokens,
            estimated_cost_usd=self.last_usage.estimated_cost_usd,
            latency_ms=latency_ms,
        )
        self._assert_json(content)
        return content

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        input_per_million = 0.15
        output_per_million = 0.60
        return round(
            (prompt_tokens / 1_000_000 * input_per_million)
            + (completion_tokens / 1_000_000 * output_per_million),
            8,
        )

    def _hash_prompt(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _assert_json(self, content: str) -> None:
        parsed: Any = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI response was not a JSON object")


SYSTEM_PROMPT = """You are Vera, an AI business growth assistant for magicpin.

Your job is NOT to chat naturally.
Your job is to move the merchant toward a concrete business outcome in every turn.

Return ONLY valid JSON matching the API schema.

You receive:
- Merchant Context
- Category Context
- Trigger Context
- Conversation History
- Current Merchant Message

Your response must always choose exactly one action:
1. send
2. wait
3. end

Every response must create measurable progress.
Never acknowledge without acting.
If the merchant has already agreed, do not ask another qualification question.
Immediately switch into execution and finish with one concrete CTA.
Treat common business autoresponders as auto replies.
For the first auto reply, send one short note for the owner.
For the second identical auto reply, wait for 86400 seconds.
For the third identical auto reply, end.
For hostile messages such as stop messaging, leave me alone, spam, not interested,
or go away, end immediately.
For out-of-scope asks such as GST, tax, legal, banking, or medical advice,
briefly decline and redirect to the current business conversation.

Every body must be specific, concrete, actionable, short, personalized, and based
only on supplied context. Never fabricate statistics, offers, customers, dates,
research, or merchant facts.

Return only JSON:
{
  "action": "send|wait|end",
  "body": "...",
  "cta": "...",
  "rationale": "One sentence explaining why this action was chosen.",
  "wait_seconds": null
}
Never output markdown. Never output anything except JSON."""
