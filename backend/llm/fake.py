from backend.llm.base import LLMError, LLMResponse, Message


class FakeProvider:
    """Scripted provider for tests: each item is reply text or an LLMError to raise."""

    def __init__(self, script: list[str | LLMError], name: str = "fake") -> None:
        self.name = name
        self.script = list(script)
        self.calls: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> LLMResponse:
        self.calls.append(messages)
        item = self.script.pop(0)
        if isinstance(item, LLMError):
            raise item
        return LLMResponse(
            text=item, provider=self.name, model="fake-1",
            input_tokens=10, output_tokens=5, latency_s=0.0,
        )
