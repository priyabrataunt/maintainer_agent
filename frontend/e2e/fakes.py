"""Fake LLM and fake GitHub for the browser end-to-end run. Everything else is real."""
import re
import time

import httpx

from backend.llm.base import LLMResponse, Message


class CitingProvider:
    """Answers every question by citing the first source it was shown."""

    name = "e2e-fake"

    def __init__(self, delay_s: float = 0.0) -> None:
        self.delay_s = delay_s  # lets the browser observe intermediate job statuses

    def complete(self, messages: list[Message]) -> LLMResponse:
        time.sleep(self.delay_s)
        text = messages[-1].content
        match = re.search(r'<source issue="#(\d+)"', text)
        if match:
            answer = f"Based on the issue discussion, see [#{match.group(1)}]."
        else:  # e.g. a summarisation call
            answer = "Notes: earlier discussion summarised."
        return LLMResponse(
            text=answer, provider=self.name, model="e2e-1",
            input_tokens=10, output_tokens=5, latency_s=0.01,
        )


def github_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/e2e/demo":
            return httpx.Response(200, json={
                "name": "demo", "description": "E2E demo repo", "stargazers_count": 1,
            })
        if path == "/repos/e2e/demo/issues":
            return httpx.Response(200, json=[{
                "number": 1, "title": "Crash on startup", "body": "segfault when config is missing",
                "state": "open", "labels": [], "created_at": "2026-01-01T00:00:00Z",
            }, {
                "number": 2, "title": "Add dark mode", "body": "please support a dark theme",
                "state": "closed", "labels": [], "created_at": "2026-01-02T00:00:00Z",
            }])
        return httpx.Response(200, json=[])

    return httpx.MockTransport(handler)
