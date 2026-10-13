"""0.3.2 — 표기차('의' 유무) 해소. 전부 FakeClient(오프라인).

라이브 근거(2026-10-13): DRF 검색은 "공공기관 운영에 관한 법률" 로도 「공공기관의 운영에 관한 법률」을
돌려주지만 정확일치에서 떨어져 UNKNOWN 이었다(openlaw-etl broken_refs 표본의 '현행 법 조회 실패').
"""

from __future__ import annotations

from lawdangle.classifier import classify
from lawdangle.client import _norm_ui
from lawdangle.models import Category, Citation, LawStatus

from test_resolver_pending_paging import FakeClient, _row
from lawdangle.resolver import LawGoKrResolver

CUR = "공공기관의 운영에 관한 법률"
CITED = "공공기관 운영에 관한 법률"


def _r(search_map):
    return LawGoKrResolver(oc="test", enrich=False, client=FakeClient(search_map=search_map))


def test_norm_ui_token_final_only():
    assert _norm_ui(CITED) == _norm_ui(CUR)
    assert _norm_ui("의료법") == "의료법"
    assert _norm_ui("의약품 등의 안전에 관한 규칙") == "의약품등안전에관한규칙"


def test_missing_ui_resolves_to_current():
    r = _r({("law", CITED, 1): [_row(CUR, "현행"), _row(CUR + " 시행령", "현행", "000002")]})
    info = r.resolve(CITED)
    assert info.status == LawStatus.CURRENT and info.current_name == CUR and info.name_form == "notation"
    res = classify(Citation(citing_law="X법", citing_article="제1조", cited_law_name=CITED, cited_article="제5조"), info)
    assert res.category == Category.A and "표기차" in res.note and res.successor_suggestion == CUR


def test_extra_ui_resolves_to_current():
    cited = "공유수면의 관리 및 매립에 관한 법률"
    cur = "공유수면 관리 및 매립에 관한 법률"
    info = _r({("law", cited, 1): [_row(cur, "현행")]}).resolve(cited)
    assert info.current_name == cur and info.name_form == "notation"


def test_ambiguous_notation_stays_unknown():
    rows = [_row("갑의 을 법", "현행", "1"), _row("갑 을의 법", "현행", "2")]   # '의'만 다른 현행 법령 둘
    info = _r({("law", "갑 을 법", 1): rows}).resolve("갑 을 법")
    assert info.status == LawStatus.UNKNOWN


def test_old_official_name_still_renamed():
    """옛 공식명이면 연혁 정확일치 → 법령ID 연속성 → RENAMED (표기차 경로로 새지 않는다)."""
    old = "공유수면의 관리 및 매립에 관한 법률"
    cur = "공유수면 관리 및 매립에 관한 법률"
    fc = FakeClient(search_map={("eflaw", old, 1): [_row(old, "연혁", "L1")]},
                    id_map={("law", "L1"): [_row(cur, "현행", "L1")]})
    info = LawGoKrResolver(oc="test", enrich=False, client=fc).resolve(old)
    assert info.status == LawStatus.RENAMED and info.current_name == cur
