"""Estimated cost of an Anthropic API call from the token counts it reports.

The token counts come straight from each response (exact); the *prices* are
this table's (an assumption to keep current: https://www.anthropic.com/pricing).
The real bill is the one in the Anthropic console, so the counter is labelled an
estimate and the prices can be overridden with ANTHROPIC_PRICE_INPUT_PER_MTOK /
ANTHROPIC_PRICE_OUTPUT_PER_MTOK.
"""
from __future__ import annotations

# USD per million tokens: (input, output). Matched by model-name prefix, so a
# dated snapshot ("claude-haiku-4-5-20251001") uses its family's price.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
# Server-side web search: $10 per 1,000 searches (the tokens it adds are in the usual counts).
WEB_SEARCH_USD = 0.01
# The app runs Haiku by default; a model missing from the table is priced as
# Haiku and flagged as such, instead of silently showing $0.
DEFAULT_PRICE: tuple[float, float] = PRICES["claude-haiku-4-5"]

# Prompt caching: a cache read costs 10% of the input price, a (5-minute)
# cache write 125%.
CACHE_READ_FACTOR = 0.10
CACHE_WRITE_FACTOR = 1.25


def price_for(model: str, override: tuple[float, float] | None = None) -> tuple[float, float, bool]:
    """(input, output, known). ``known`` is False for a model not in the table."""
    if override is not None and override[0] > 0 and override[1] > 0:
        return override[0], override[1], True
    for prefix, price in PRICES.items():
        if model.startswith(prefix):
            return price[0], price[1], True
    return DEFAULT_PRICE[0], DEFAULT_PRICE[1], False


def cost_usd(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    override: tuple[float, float] | None = None,
) -> float:
    """Estimated dollars. The API reports cached tokens separately from
    ``input_tokens``, so the four counts are additive."""
    p_in, p_out, _ = price_for(model, override)
    per_token_in = p_in / 1_000_000
    return (
        input_tokens * per_token_in
        + output_tokens * (p_out / 1_000_000)
        + cache_read_tokens * per_token_in * CACHE_READ_FACTOR
        + cache_write_tokens * per_token_in * CACHE_WRITE_FACTOR
    )
