"""lawdangle — Dead Cross-Reference Detector for Korean Statutes.

현행 법령이 인용하는 대상 법령의 폐지·개명·이관·사문화를 탐지하고 5분류로 태깅한다.
배포명 `lawdangle-kr` / import명 `lawdangle` (DESIGN.md 네이밍).
"""

from __future__ import annotations

from .classifier import classify
from .mapper import MappingSuggestion, rank_correspondence, suggest_mapping
from .models import (
    Category,
    Citation,
    Confidence,
    HistoryInfo,
    LawStatus,
    Result,
)
from .parser import parse_citations
from .resolver import FixtureResolver, LawGoKrResolver, Resolver

__version__ = "0.1.0"

__all__ = [
    "Category",
    "Citation",
    "Confidence",
    "HistoryInfo",
    "LawStatus",
    "Result",
    "classify",
    "parse_citations",
    "Resolver",
    "FixtureResolver",
    "LawGoKrResolver",
    "suggest_mapping",
    "rank_correspondence",
    "MappingSuggestion",
    "__version__",
]
