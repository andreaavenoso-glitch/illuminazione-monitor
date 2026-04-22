"""Public-lighting perimeter classifier. Implements spec §10.2:

    positive score on LIGHTING_INCLUDE tokens (+2 each)
    negative score on LIGHTING_EXCLUDE tokens (-3 each)
    bonus +2 if text contains a lighting-specific CPV
    threshold: net score >= 1 to be considered in-scope
"""
from __future__ import annotations

from dataclasses import dataclass

from parsing_rules.keywords import LIGHTING_EXCLUDE, LIGHTING_INCLUDE
from parsing_rules.regex import contains_lighting_cpv


@dataclass(frozen=True)
class PerimeterScore:
    score: int
    include_hits: tuple[str, ...]
    exclude_hits: tuple[str, ...]
    cpv_match: bool

    @property
    def in_scope(self) -> bool:
        return self.score >= 1


def score_perimeter(text: str | None) -> PerimeterScore:
    if not text:
        return PerimeterScore(score=0, include_hits=(), exclude_hits=(), cpv_match=False)

    low = text.lower()
    include_hits = tuple(kw for kw in LIGHTING_INCLUDE if kw in low)
    exclude_hits = tuple(kw for kw in LIGHTING_EXCLUDE if kw in low)
    cpv_match = contains_lighting_cpv(text)

    score = 2 * len(include_hits) - 3 * len(exclude_hits)
    if cpv_match:
        score += 2

    return PerimeterScore(
        score=score,
        include_hits=include_hits,
        exclude_hits=exclude_hits,
        cpv_match=cpv_match,
    )


def is_in_lighting_perimeter(text: str | None) -> bool:
    return score_perimeter(text).in_scope
