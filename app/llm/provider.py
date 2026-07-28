"""LLM provider interface, OpenAI implementation, and deterministic fallbacks."""

from __future__ import annotations

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from groq import Groq

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

    @abstractmethod
    def health_check(self) -> bool:
        """Return whether the provider is configured and reachable."""

    @abstractmethod
    def retry(self, prompt: str, cache_key: str | None = None) -> str:
        """Retry a provider call according to provider policy."""


class FallbackTemplateProvider(LLMProvider):
    """Deterministic category templates used when the model path is unavailable."""

    def compose(self, prompt: str, cache_key: str | None = None) -> str:
        prompt_lower = prompt.lower()
        if "dentists" in prompt_lower or "peer_clinical" in prompt_lower:
            message = (
                "Quick note: one relevant dental update is ready from the facts above. "
                "Want me to draft the patient-facing WhatsApp from it?"
            )
        elif "restaurants" in prompt_lower:
            message = (
                "Quick operational nudge from today's trigger. Want me to turn this "
                "into a short customer message using your active offer?"
            )
        elif "salons" in prompt_lower:
            message = (
                "Quick salon update: this trigger looks useful for your next post. "
                "Want me to draft a 4-line WhatsApp for customers?"
            )
        elif "gyms" in prompt_lower:
            message = (
                "Quick fitness update from your dashboard. Want me to draft a simple "
                "member message for this?"
            )
        elif "pharmacies" in prompt_lower:
            message = (
                "Quick pharmacy update: this needs a precise customer note. Want me "
                "to draft it from the verified details?"
            )
        else:
            message = "Quick update from Vera. Want me to draft the next message?"

        return json.dumps(
            {
                "message": message,
                "cta": "open_ended" if "?" in message else "none",
                "rationale": "Deterministic fallback template used.",
            }
        )

    def health_check(self) -> bool:
        return True

    def retry(self, prompt: str, cache_key: str | None = None) -> str:
        return self.compose(prompt, cache_key=cache_key)


class MockLLMProvider(FallbackTemplateProvider):
    """Backward-compatible test provider alias."""


class OpenAIProvider(LLMProvider):
    """Production Groq provider with retries, caching, and cost logging."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        fallback_provider: LLMProvider | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 0.5,
        azure_endpoint: str | None = None,
        azure_api_version: str | None = None,
        use_azure: bool | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("magicpin", "")
        self.model_name = model_name or "llama-3.3-70b-versatile"
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.azure_endpoint = azure_endpoint or ""
        self.azure_api_version = azure_api_version or "2025-01-01-preview"
        self.use_azure = False
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
        """Check whether the configured provider is reachable."""
        if not self.api_key:
            return False

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                if self.use_azure:
                    url = f"{self.azure_endpoint.rstrip('/')}/openai/deployments/{self.model_name}?api-version={self.azure_api_version}"
                    headers = {"api-key": self.api_key}
                else:
                    url = f"https://api.openai.com/v1/models/{self.model_name}"
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                response = client.get(url, headers=headers)
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
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 500,
        }
        payload["model"] = self.model_name
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "vera_message",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "message": {"type": "string"},
                        "cta": {
                            "type": "string",
                            "enum": ["binary_yes_stop", "open_ended", "none"],
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": ["message", "cta", "rationale"],
                },
            },
        }

        client = Groq(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model_name,
            messages=payload["messages"],
            temperature=payload["temperature"],
            max_tokens=payload["max_tokens"],
            response_format={"type": "json_object"},
        )
        data = response.model_dump()

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

    def _chat_completions_url(self) -> str:
        return OPENAI_CHAT_COMPLETIONS_URL

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost conservatively when exact model pricing is configured elsewhere."""
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


SYSTEM_PROMPT = """You are Vera's language realization layer.
Convert the provided Decision Card and minimal facts into one WhatsApp message.
You must not choose opportunities, rank triggers, create offers, invent facts,
invent prices, invent dates, invent research, invent statistics, change the CTA,
or override the Decision Card. Return valid JSON only with exactly these keys:
message, cta, rationale."""
