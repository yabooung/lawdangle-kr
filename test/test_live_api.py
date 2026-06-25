"""라이브 법제처 API 통합 테스트 — 상태 판정만 검증.

OC 키(.env의 oc= 또는 LAW_OC 환경변수)와 네트워크가 있을 때만 실행.
후속법(successor)은 검색 API로 얻을 수 없으므로 여기서 검증하지 않는다
(그건 수동 플래그의 영역 — DESIGN §3 ③).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lawdangle.models import LawStatus
from lawdangle.resolver import LawGoKrResolver


def _load_oc() -> str | None:
    oc = os.environ.get("LAW_OC")
    if oc:
        return oc
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().lower().startswith("oc="):
                return line.split("=", 1)[1].strip()
    return None


OC = _load_oc()
pytestmark = pytest.mark.skipif(OC is None, reason="OC 키 없음 — 라이브 테스트 건너뜀")


@pytest.fixture(scope="module")
def resolver():
    return LawGoKrResolver(OC)


def test_current_law_detected(resolver):
    info = resolver.resolve("민법")
    assert info.status == LawStatus.CURRENT
    assert info.current_name and "민법" in info.current_name


def test_repealed_law_detected(resolver):
    # 국유재산관리특별회계법: 2007.1.1 폐지 (D fixture의 대상)
    info = resolver.resolve("국유재산관리특별회계법")
    assert info.status == LawStatus.REPEALED
    assert info.raw.get("_repeal_explicit") is True  # 제개정구분명 "폐지"


def test_absorbed_signal_extracted(resolver):
    # 폐지법 상세 제개정이유: "일반회계로 통합운영" → absorbed (후속법 없음, D 강신호)
    info = resolver.resolve("국유재산관리특별회계법")
    assert info.absorbed is True
    assert info.successor_candidates == []


def test_successor_candidates_extracted(resolver):
    # 국가균형발전 특별법: 제개정이유 산문에서 후속법 후보 자동 추출
    info = resolver.resolve("국가균형발전 특별법")
    assert info.status == LawStatus.REPEALED
    assert len(info.successor_candidates) >= 1


def test_renamed_law_detected_via_id(resolver):
    # 기부금품의 모집 및 사용에 관한 법률 → (법령ID 연속) 기부문화 활성화 …으로 개명
    info = resolver.resolve("기부금품의 모집 및 사용에 관한 법률")
    assert info.status == LawStatus.RENAMED
    assert info.current_name and "기부문화" in info.current_name
    assert info.alive_articles  # 현행본 조문 집합 확보


def test_repealed_not_misclassified_as_rename(resolver):
    # 국가균형발전 특별법: 법령ID가 현행에 없음 → 개명 아님, 폐지로 남아야
    info = resolver.resolve("국가균형발전 특별법")
    assert info.status == LawStatus.REPEALED


def test_official_abbreviation_resolved(resolver):
    # 공식 약칭사전(lsAbrv): '정보통신망법' → 풀네임, 현행
    info = resolver.resolve("정보통신망법")
    assert info.status == LawStatus.CURRENT
    assert info.name_form == "alias"
    assert info.current_name and "정보통신망" in info.current_name


def test_partial_name_resolved(resolver):
    # 부분명(앞부분 생략): '재생에너지 개발ㆍ이용ㆍ보급 촉진법' → 신에너지 및 …
    info = resolver.resolve("재생에너지 개발ㆍ이용ㆍ보급 촉진법")
    assert info.status == LawStatus.CURRENT
    assert info.name_form == "partial"
    assert info.current_name and info.current_name.startswith("신에너지")


def test_tabeop_repeal_successor_backtrace(resolver):
    # 타법폐지 역추적: 저탄소 녹색성장 기본법 → 「기후위기…탄소중립…기본법」
    info = resolver.resolve("저탄소 녹색성장 기본법")
    assert info.status == LawStatus.REPEALED
    assert any("탄소중립" in c for c in info.successor_candidates)


def test_run_law_fills_citing_article(resolver):
    # 법령명 분석: 공유수면법 본문에서 §13의 국가균형발전법 인용을 잡고 죽은 참조로 분류
    from lawdangle import run_law

    results = run_law("공유수면 관리 및 매립에 관한 법률", resolver)
    assert results, "인용이 추출되어야 함"
    dead = [r for r in results if r.category and "국가균형발전" in r.citation.cited_law_name]
    assert dead, "국가균형발전 특별법 죽은 인용이 잡혀야 함"
    assert dead[0].citation.citing_article  # 인용하는 조(citing_article) 채워짐


def test_auto_discover_split_successor(resolver):
    # 분할 이관 자동 발견: §17② 후속법을 안 알려줘도 본문으로 「지역 산업위기…법」 발견
    from lawdangle.mapper import suggest_mapping_auto

    s = suggest_mapping_auto(resolver, "국가균형발전 특별법", "제17조제2항")
    assert s is not None
    assert "산업위기" in s.successor_law            # 조항의 실제 후속법 자동 발견
    assert any(c.article.startswith("제10조") for c in s.candidates)  # §10 대응


def test_unknown_law(resolver):
    info = resolver.resolve("존재하지않는가짜법령명1234")
    assert info.status == LawStatus.UNKNOWN


def test_mapper_finds_design_answer(resolver):
    # DESIGN §2 B케이스: 국가균형발전법 §17② 제도 → 「지역 산업위기…특별법」 §10.
    # 연혁 walk로 삭제 전 실본문을 찾아 본문 유사도 #1 후보가 제10조여야 한다.
    from lawdangle.mapper import suggest_mapping

    s = suggest_mapping(
        resolver,
        "국가균형발전 특별법",
        "제17조제2항",
        "지역 산업위기 대응 및 지역경제 회복을 위한 특별법",
    )
    assert s.old_article_version is not None  # 삭제 전 실본문 확보
    assert s.candidates, "후보가 추출되어야 함"
    # DESIGN 정답 §17②→§10 이 상위 후보에 포함(항 정밀화로 '제10조제1항' 형태 가능)
    top3 = [c.article for c in s.candidates]
    assert any(a.startswith("제10조") for a in top3)
