import hashlib
import math
import re
from typing import Protocol

import httpx

from backend.config import settings
from backend.llm.base import LLMError
from backend.models.document_chunk import EMBEDDING_DIM


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Deterministic bag-of-words embeddings: no network, similar texts land close together.

    For development and tests only; retrieval quality is far below a real model.
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % self.dim
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector


class OpenAIEmbedder:
    URL = "https://api.openai.com/v1/embeddings"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key.get_secret_value()
        self.model = model or settings.openai_embedding_model
        self._client = httpx.Client(timeout=60, transport=transport)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts, "dimensions": EMBEDDING_DIM},
            )
        except httpx.TransportError as exc:
            raise LLMError(f"network error: {exc}", retryable=True) from exc
        if response.status_code != 200:
            retryable = response.status_code == 429 or response.status_code >= 500
            raise LLMError(f"HTTP {response.status_code}: {response.text[:200]}", retryable)
        items = sorted(response.json()["data"], key=lambda d: d["index"])
        return [item["embedding"] for item in items]


def get_embedder() -> Embedder:
    if settings.embedding_provider == "openai":
        return OpenAIEmbedder()
    return HashEmbedder()
