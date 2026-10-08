import time

import httpx

from backend.config import settings
from backend.llm.base import LLMError, LLMResponse, Message
from backend.llm.pricing import calculate_cost


def _post(client: httpx.Client, url: str, headers: dict, body: dict) -> dict:
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.TransportError as exc:
        raise LLMError(f"network error: {exc}", retryable=True) from exc
    if response.status_code != 200:
        retryable = response.status_code == 429 or response.status_code >= 500
        raise LLMError(f"HTTP {response.status_code}: {response.text[:200]}", retryable)
    return response.json()


class AnthropicProvider:
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or settings.anthropic_api_key.get_secret_value()
        self.model = model or settings.anthropic_model
        self.max_tokens = max_tokens
        self._client = httpx.Client(timeout=60, transport=transport)

    def complete(self, messages: list[Message]) -> LLMResponse:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [m.model_dump() for m in messages if m.role != "system"],
        }
        if system:
            body["system"] = system
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

        start = time.perf_counter()
        data = _post(self._client, self.URL, headers, body)
        latency = time.perf_counter() - start

        usage = data["usage"]
        text = "".join(b["text"] for b in data["content"] if b["type"] == "text")
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            latency_s=latency,
            cost_usd=calculate_cost(self.model, usage["input_tokens"], usage["output_tokens"]),
        )


class OpenAIProvider:
    name = "openai"
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key.get_secret_value()
        self.model = model or settings.openai_model
        self._client = httpx.Client(timeout=60, transport=transport)

    def complete(self, messages: list[Message]) -> LLMResponse:
        body = {"model": self.model, "messages": [m.model_dump() for m in messages]}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        start = time.perf_counter()
        data = _post(self._client, self.URL, headers, body)
        latency = time.perf_counter() - start

        usage = data["usage"]
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            provider=self.name,
            model=data.get("model", self.model),
            input_tokens=usage["prompt_tokens"],
            output_tokens=usage["completion_tokens"],
            latency_s=latency,
            cost_usd=calculate_cost(self.model, usage["prompt_tokens"], usage["completion_tokens"]),
        )
