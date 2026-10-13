"""lawdangle — Dead Cross-Reference Detector for Korean Statutes.

현행 법령이 인용하는 대상 법령의 폐지·개명·이관·사문화를 탐지하고 5분류로 태깅한다.
배포명 `lawdangle-kr` / import명 `lawdangle` (DESIGN.md 네이밍).
"""

from __future__ import annotations

from .classifier import classify
from .cli import run, run_law
from .mapper import (
    MappingSuggestion,
    discover_successors,
    rank_correspondence,
    suggest_mapping,
    suggest_mapping_auto,
)
from .client import LawApiError, LawClient
from .models import (
    Category,
    Citation,
    Confidence,
    HistoryInfo,
    LawSearchResult,
    LawStatus,
    LawText,
    Result,
)
from .parser import parse_citations
from .resolver import FixtureResolver, LawGoKrResolver, Resolver
from .search import get_law_text, search_law

__version__ = "0.3.2"

__all__ = [
    "Category",
    "Citation",
    "Confidence",
    "HistoryInfo",
    "LawStatus",
    "LawSearchResult",
    "LawText",
    "Result",
    "classify",
    "run",
    "run_law",
    "parse_citations",
    "search_law",
    "get_law_text",
    "Resolver",
    "FixtureResolver",
    "LawGoKrResolver",
    "LawClient",
    "LawApiError",
    "suggest_mapping",
    "suggest_mapping_auto",
    "discover_successors",
    "rank_correspondence",
    "MappingSuggestion",
    "__version__",
]
