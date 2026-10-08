from typing import Literal, Protocol

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    cost_usd: float | None = None


class LLMError(Exception):
    """A failed LLM call. `retryable` is True for 429 and 5xx responses."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str

    def complete(self, messages: list[Message]) -> LLMResponse: ...
