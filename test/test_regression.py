"""회귀 테스트 — 실제 판정례를 fixture로 고정(오프라인·결정적).

각 fixture는 라이브 API로 확인한 실제 법령 전이(2026-07)를 '정비 후' 데이터로 박은 것.
출력 category가 기대값과 다르면 회귀 실패. A~E 중 E는 classify가 자동 단정하지 않으므로
(보수적으로 D 기본 + 수동 플래그) 회귀는 A/B/C/D를 다룬다 — E 판단은 사람 몫.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lawdangle import parse_citations
from lawdangle.classifier import classify
from lawdangle.resolver import FixtureResolver

FIXTURES = Path(__file__).parent / "fixtures"

# 등급별 실제 판정례 — (fixture, 기대 category).
CASES = [
    "gibu.json",          # A — 개명(기부금품법 → 기부문화 활성화법)
    "gongyusumyeon.json",  # B — 이관(국가균형발전법 §17② → 지역산업위기법)
    "jeotanso.json",      # B — 타법폐지 이관(저탄소녹색성장 → 탄소중립기본법)
    "eumbin.json",        # C — 분할 승계(음비게법 → 영화비디오물+게임산업)
    "deunggi.json",       # D — 흡수(국유재산관리특별회계 → 일반회계)
    "sahoeboho.json",     # D — 폐지·무신호(자체완결 D 기본, E는 수동)
]


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


# 분류를 가르는 신호(status·후속법 수)가 fixture별로 정확히 잡히는지.
_SIGNAL = [
    ("eumbin.json", "음반ㆍ비디오물 및 게임물에 관한 법률", lambda i: len(i.successors) >= 2),   # C
    ("jeotanso.json", "저탄소 녹색성장 기본법", lambda i: len(i.successors) == 1),                # B
    ("sahoeboho.json", "사회보호법", lambda i: i.successors == []),                               # D
]


@pytest.mark.parametrize("fixture_name,cited,check", _SIGNAL)
def test_successor_signal(fixture_name, cited, check):
    path = FIXTURES / fixture_name
    info = FixtureResolver.from_files(path).resolve(cited)
    assert check(info), f"{fixture_name}: 후속법 신호가 기대와 다름 (successors={info.successors})"
