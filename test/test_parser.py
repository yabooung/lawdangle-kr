"""Parser 단위 테스트 — 인용 추출 + 조문 코드 변환."""

from __future__ import annotations

from lawdangle.parser import article_to_code, parse_citations


def test_extract_basic():
    text = "「국가균형발전 특별법」 제17조제2항에 따른 사업"
    cites = parse_citations(text)
    assert len(cites) == 1
    assert cites[0].cited_law_name == "국가균형발전 특별법"
    assert cites[0].cited_article == "제17조제2항"


def test_strips_inner_whitespace():
    cites = parse_citations("「민법」 제3조 제2항")
    assert cites[0].cited_article == "제3조제2항"


def test_filters_non_law_brackets():
    # 별표/고시명은 법령명이 아님 → 제외
    cites = parse_citations("「공무원 보수규정 별표1」 및 「민법」 제1조")
    names = [c.cited_law_name for c in cites]
    assert "민법" in names
    assert all("별표" not in n for n in names)


def test_multiple_citations_one_text():
    text = "「형법」 제10조와 「민법」 제3조를 본다"
    cites = parse_citations(text)
    assert {c.cited_law_name for c in cites} == {"형법", "민법"}


def test_article_to_code():
    assert article_to_code("제5조") == "000500"
    assert article_to_code("제5조의2") == "000502"
    assert article_to_code("제17조제2항") == "001700"
