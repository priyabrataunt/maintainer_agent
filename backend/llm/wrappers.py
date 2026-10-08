import logging
import time
from collections.abc import Callable

from backend.llm.base import LLMError, LLMProvider, LLMResponse, Message

logger = logging.getLogger("backend.llm")


class RetryingProvider:
    """Retry retryable failures (429/5xx/network) with exponential backoff."""

    def __init__(
        self,
        inner: LLMProvider,
        max_attempts: int = 3,
        base_delay_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.max_attempts = max_attempts
        self.base_delay_s = base_delay_s
        self._sleep = sleep

    def complete(self, messages: list[Message]) -> LLMResponse:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.inner.complete(messages)
            except LLMError as exc:
                if not exc.retryable or attempt == self.max_attempts:
                    raise
                delay = self.base_delay_s * 2 ** (attempt - 1)
                logger.warning("%s attempt %d failed (%s); retrying in %.1fs",
                               self.name, attempt, exc, delay)
                self._sleep(delay)
        raise AssertionError("unreachable")


class FallbackProvider:
    """Try each provider in order; raise the last error if all fail."""

    name = "fallback"

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("FallbackProvider needs at least one provider")
        self.providers = providers

    def complete(self, messages: list[Message]) -> LLMResponse:
        last_error: LLMError | None = None
        for provider in self.providers:
            try:
                return provider.complete(messages)
            except LLMError as exc:
                logger.warning("%s failed (%s); trying next provider", provider.name, exc)
                last_error = exc
        raise last_error


class LoggingProvider:
    """Log provider, model, tokens in/out, latency and cost for every call."""

    def __init__(self, inner: LLMProvider) -> None:
        self.inner = inner
        self.name = inner.name

    def complete(self, messages: list[Message]) -> LLMResponse:
        response = self.inner.complete(messages)
        logger.info(
            "llm_call provider=%s model=%s tokens_in=%d tokens_out=%d latency_s=%.3f cost_usd=%s",
            response.provider, response.model, response.input_tokens,
            response.output_tokens, response.latency_s, response.cost_usd,
        )
        return response
