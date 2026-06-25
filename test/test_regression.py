"""회귀 테스트 — DESIGN.md §2 검증된 2케이스 고정.

출력이 B/D로 안 나오면 회귀 실패.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lawdangle import parse_citations
from lawdangle.classifier import classify
from lawdangle.resolver import FixtureResolver

FIXTURES = Path(__file__).parent / "fixtures"
CASES = ["gongyusumyeon.json", "deunggi.json"]


@pytest.mark.parametrize("fixture_name", CASES)
def test_regression_category(fixture_name):
    path = FIXTURES / fixture_name
    data = json.loads(path.read_text(encoding="utf-8"))
    resolver = FixtureResolver.from_files(path)

    citations = parse_citations(data["text"], citing_law=data["citing_law"])
    # 정답 대상 법령을 인용한 레코드 찾기
    target = next(
        c for c in citations if c.cited_law_name == data["expected"]["cited_law_name"]
    )

    result = classify(target, resolver.resolve(target.cited_law_name))
    assert result.category is not None
    assert result.category.name == data["expected"]["category"], (
        f"{fixture_name}: expected {data['expected']['category']}, "
        f"got {result.category.name} — {result.note}"
    )


def test_gongyusumyeon_is_B_with_successor():
    path = FIXTURES / "gongyusumyeon.json"
    resolver = FixtureResolver.from_files(path)
    info = resolver.resolve("국가균형발전 특별법")
    assert len(info.successors) == 1  # 후속법 단일 → B 분기


def test_deunggi_is_D_no_successor():
    path = FIXTURES / "deunggi.json"
    resolver = FixtureResolver.from_files(path)
    info = resolver.resolve("국유재산관리특별회계법")
    assert info.successors == []  # 후속법 없음 → D/E 후보(수동)
