"""Classifier 단위 테스트 — 5분류 의사결정 트리 + 자동/수동 경계."""

from __future__ import annotations

from lawdangle.classifier import classify
from lawdangle.models import Category, Citation, Confidence, HistoryInfo, LawStatus


def _cite(law="대상법", art="제1조"):
    return Citation("인용법", "제1조", law, art)


def test_current_same_name_is_normal():
    h = HistoryInfo(status=LawStatus.CURRENT, current_name="대상법")
    r = classify(_cite(), h)
    assert r.category is None  # 정상 — 분류 대상 아님


def test_alias_resolves_to_A_with_note():
    h = HistoryInfo(status=LawStatus.CURRENT, current_name="정식 풀네임 법률", name_form="alias")
    r = classify(_cite("약칭법"), h)
    assert r.category == Category.A
    assert "약칭" in r.note


def test_partial_name_resolves_to_A():
    h = HistoryInfo(status=LawStatus.CURRENT, current_name="신에너지 및 재생에너지법", name_form="partial")
    r = classify(_cite("재생에너지법"), h)
    assert r.category == Category.A
    assert "부분명" in r.note


def test_renamed_is_A():
    h = HistoryInfo(status=LawStatus.RENAMED, current_name="새이름법")
    r = classify(_cite("옛이름법"), h)
    assert r.category == Category.A
    assert r.successor_suggestion == "새이름법"


def test_current_name_mismatch_is_A():
    h = HistoryInfo(status=LawStatus.CURRENT, current_name="현행명")
    r = classify(_cite("인용에쓴옛명"), h)
    assert r.category == Category.A


def test_rename_with_article_preserved_is_A():
    # 개명 + 인용 조문이 현행본에 살아있음 → 깨끗한 A
    h = HistoryInfo(
        status=LawStatus.RENAMED, current_name="새이름법",
        alive_articles={"제5조", "제17조"},
    )
    r = classify(_cite("옛이름법", "제5조제2항"), h)
    assert r.category == Category.A


def test_rename_with_article_gone_is_B():
    # 개명됐으나 인용 조문이 현행본에 없음(삭제/재번호) → B
    h = HistoryInfo(
        status=LawStatus.RENAMED, current_name="새이름법",
        alive_articles={"제3조", "제4조"},  # 제17조 없음
    )
    r = classify(_cite("옛이름법", "제17조제2항"), h)
    assert r.category == Category.B
    assert r.flag is True


def test_rename_no_article_info_defaults_A():
    # 조문 정보 못 가져온 경우(alive_articles 비었음) → A 가정
    h = HistoryInfo(status=LawStatus.RENAMED, current_name="새이름법")
    r = classify(_cite("옛이름법", "제17조"), h)
    assert r.category == Category.A


def test_repealed_single_successor_is_B_flagged():
    h = HistoryInfo(status=LawStatus.REPEALED, successors=["승계법"])
    r = classify(_cite(), h)
    assert r.category == Category.B
    assert r.flag is True  # 조문 대응 확인 필요


def test_repealed_multi_successor_is_C_manual():
    h = HistoryInfo(status=LawStatus.REPEALED, successors=["법1", "법2"])
    r = classify(_cite(), h)
    assert r.category == Category.C
    assert r.confidence == Confidence.MANUAL
    assert r.flag is True


def test_repealed_no_successor_is_D_manual():
    h = HistoryInfo(status=LawStatus.REPEALED, successors=[])
    r = classify(_cite(), h)
    assert r.category == Category.D
    assert r.confidence == Confidence.MANUAL  # D/E 자동 단정 금지
    assert r.flag is True


def test_repealed_absorbed_is_D_strong():
    h = HistoryInfo(
        status=LawStatus.REPEALED, successors=[], absorbed=True,
        repeal_reason="일반회계로 통합운영하려는 것임",
    )
    r = classify(_cite(), h)
    assert r.category == Category.D
    assert "흡수통합" in r.note


def test_repealed_single_candidate_is_B():
    # 후속법 후보 1개(타법폐지 역추적/제개정이유) → B(이관), 수동 플래그
    h = HistoryInfo(
        status=LawStatus.REPEALED, successors=[],
        successor_candidates=["승계후보법"],
    )
    r = classify(_cite(), h)
    assert r.category == Category.B
    assert r.flag is True
    assert r.successor_suggestion == "승계후보법"


def test_repealed_multi_candidates_is_C():
    h = HistoryInfo(
        status=LawStatus.REPEALED, successors=[],
        successor_candidates=["법갑", "법을", "법병"],
    )
    r = classify(_cite(), h)
    assert r.category == Category.C
    assert r.confidence == Confidence.MANUAL


def test_confirmed_successor_beats_candidates():
    # 확정 후속법(successors)이 있으면 후보보다 우선 → B 자동
    h = HistoryInfo(
        status=LawStatus.REPEALED, successors=["확정승계법"],
        successor_candidates=["딴후보"],
    )
    r = classify(_cite(), h)
    assert r.category == Category.B


def test_normalize_middot_not_rename():
    # 가운뎃점/띄어쓰기 차이는 개명 아님 (함정 1)
    h = HistoryInfo(status=LawStatus.CURRENT, current_name="공유수면 관리ㆍ매립에 관한 법률")
    r = classify(_cite("공유수면 관리·매립에관한 법률"), h)
    assert r.category is None


def test_severity_order():
    assert Category.E.severity < Category.C.severity < Category.D.severity
    assert Category.D.severity < Category.B.severity < Category.A.severity
