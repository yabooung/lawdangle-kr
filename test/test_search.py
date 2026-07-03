"""search_law / get_law_text 단위 테스트 — FakeClient 주입(네트워크 불필요)."""

from __future__ import annotations

import pytest

from lawdangle.resolver import LawGoKrResolver
from lawdangle.search import get_law_text, normalize_article_key, search_law


class FakeClient:
    """LawClient 대역 — (target, query/mst) 키로 canned 응답 반환."""

    def __init__(self, search_map=None, service_map=None):
        self.search_map = search_map or {}
        self.service_map = service_map or {}

    def search(self, target, query):
        return self.search_map.get((target, query), {})

    def search_by_id(self, target, law_id):
        return self.search_map.get((target, f"ID:{law_id}"), {})

    def service(self, target, mst):
        return self.service_map.get((target, mst), {})

    def get(self, endpoint, extra, *, retries=2):  # _abbr()가 부를 수 있음
        return {}


def _search_resp(rows):
    return {"LawSearch": {"law": rows}}


def _detail(articles):
    """{조번호: 본문} → lawService.do 상세 형태."""
    jos = [
        {"조문번호": no, "조문내용": body}
        for no, body in articles.items()
    ]
    return {"법령": {"조문": {"조문단위": jos}}}


def _resolver(search_map=None, service_map=None):
    return LawGoKrResolver("OC", client=FakeClient(search_map, service_map))


# --- normalize_article_key --------------------------------------------- #


def test_normalize_article_key():
    assert normalize_article_key("제5조") == "제5조"
    assert normalize_article_key("5") == "제5조"
    assert normalize_article_key("제5조의2") == "제5조의2"
    assert normalize_article_key("제5조제2항") == "제5조"  # 항은 조로 환원
    with pytest.raises(ValueError):
        normalize_article_key("법령")


# --- search_law -------------------------------------------------------- #


def test_search_law_lists_all_and_current_only():
    r = _resolver(search_map={
        ("law", "민법"): _search_resp([
            {"법령ID": "1", "법령명한글": "민법", "현행연혁코드": "현행",
             "시행일자": "20230101", "법종구분명": "법률", "법령일련번호": "100"},
            {"법령ID": "1", "법령명한글": "민법", "현행연혁코드": "연혁",
             "시행일자": "20200101", "법령일련번호": "90"},
        ]),
    })
    allr = search_law(r, "민법")
    assert [x.status for x in allr] == ["현행", "연혁"]
    assert allr[0].mst == "100" and allr[0].law_type == "법률"

    cur = search_law(r, "민법", current_only=True)
    assert len(cur) == 1 and cur[0].is_current


def test_search_law_limit():
    rows = [{"법령ID": str(i), "법령명한글": f"법{i}", "현행연혁코드": "현행",
             "시행일자": "20230101"} for i in range(5)]
    r = _resolver(search_map={("law", "법"): _search_resp(rows)})
    assert len(search_law(r, "법", limit=3)) == 3


def test_search_law_empty_returns_list():
    assert search_law(_resolver(), "존재하지않는법") == []


# --- get_law_text ------------------------------------------------------ #


def test_get_law_text_full_and_single_article():
    search_map = {("law", "민법"): _search_resp([
        {"법령명한글": "민법", "현행연혁코드": "현행", "시행일자": "20230101",
         "법령일련번호": "100"},
    ])}
    service_map = {("law", "100"): _detail({"1": "제1조 본문", "2": "제2조 본문"})}
    r = _resolver(search_map, service_map)

    full = get_law_text(r, "민법")
    assert full.name == "민법"
    assert set(full.articles) == {"제1조", "제2조"}
    assert full.requested_article is None

    one = get_law_text(r, "민법", "제2조")
    assert one.requested_article == "제2조"
    assert list(one.articles) == ["제2조"]


def test_get_law_text_missing_article_raises():
    search_map = {("law", "민법"): _search_resp([
        {"법령명한글": "민법", "현행연혁코드": "현행", "시행일자": "20230101",
         "법령일련번호": "100"},
    ])}
    service_map = {("law", "100"): _detail({"1": "제1조 본문"})}
    r = _resolver(search_map, service_map)
    with pytest.raises(ValueError):
        get_law_text(r, "민법", "제99조")


def test_get_law_text_unknown_law_raises():
    with pytest.raises(ValueError):
        get_law_text(_resolver(), "없는법령")
