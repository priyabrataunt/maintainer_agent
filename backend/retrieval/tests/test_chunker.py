import pytest

from backend.retrieval.chunker import chunk_text
from backend.retrieval.tokens import count_tokens


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_count_tokens():
    assert count_tokens("") == 0
    assert count_tokens("abcd") == 1
    assert count_tokens("abcde") == 2


def test_short_text_is_one_chunk():
    assert chunk_text("hello world", max_tokens=50, overlap_tokens=5) == ["hello world"]


def test_empty_text_has_no_chunks():
    assert chunk_text("   ", max_tokens=50, overlap_tokens=5) == []


def test_chunks_respect_max_tokens():
    chunks = chunk_text(words(200), max_tokens=20, overlap_tokens=5)

    assert len(chunks) > 1
    assert all(count_tokens(c + " ") <= 20 + 2 for c in chunks)


def test_consecutive_chunks_overlap():
    chunks = chunk_text(words(100), max_tokens=20, overlap_tokens=6)

    for previous, current in zip(chunks, chunks[1:]):
        assert previous.split()[-1] in current.split()


def test_every_word_is_covered_and_order_preserved():
    text = words(150)
    chunks = chunk_text(text, max_tokens=25, overlap_tokens=8)

    seen: list[str] = []
    for chunk in chunks:
        for word in chunk.split():
            if word not in seen:
                seen.append(word)
    assert seen == text.split()


def test_makes_progress_with_zero_overlap():
    chunks = chunk_text(words(50), max_tokens=10, overlap_tokens=0)

    assert " ".join(chunks).split() == words(50).split()


def test_oversized_single_word_still_emitted():
    chunks = chunk_text("x" * 100 + " tail", max_tokens=5, overlap_tokens=0)

    assert chunks[0] == "x" * 100
    assert chunks[-1] == "tail"


@pytest.mark.parametrize("max_tokens,overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_parameters_rejected(max_tokens, overlap):
    with pytest.raises(ValueError):
        chunk_text("a b c", max_tokens=max_tokens, overlap_tokens=overlap)
