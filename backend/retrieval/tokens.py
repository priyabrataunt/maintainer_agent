import math


def count_tokens(text: str) -> int:
    """Approximate token count (~4 characters per token for English text).

    A real tokenizer can replace this later without changing callers; the
    chunker and budgeter only depend on this function.
    """
    return math.ceil(len(text) / 4) if text else 0
