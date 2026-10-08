# USD per million tokens: (input, output). Keyed by exact model version.
# Fill in / verify against the provider's pricing page before trusting costs;
# unknown models yield cost None rather than a guess.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4.1-2025-04-14": (2.00, 8.00),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = PRICES_PER_MTOK.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
