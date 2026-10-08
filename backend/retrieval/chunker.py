from collections.abc import Callable

from backend.retrieval.tokens import count_tokens


def chunk_text(
    text: str,
    max_tokens: int = 200,
    overlap_tokens: int = 40,
    counter: Callable[[str], int] = count_tokens,
) -> list[str]:
    """Split `text` into word-aligned chunks of <= `max_tokens`, overlapping ~`overlap_tokens`."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap_tokens must be >= 0 and < max_tokens")

    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start
        used = 0
        while end < len(words):
            cost = counter(words[end] + " ")
            if used + cost > max_tokens and end > start:
                break
            used += cost
            end += 1
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break

        # Step back from `end` to carry ~overlap_tokens of trailing words forward.
        next_start = end
        carried = 0
        while next_start > start + 1:
            cost = counter(words[next_start - 1] + " ")
            if carried + cost > overlap_tokens:
                break
            next_start -= 1
            carried += cost
        start = next_start
    return chunks
