"""법령 검색·조문 조회 공개 API (Phase 1).

korean-law-mcp 의 원격 서버 없이도 로컬에서 법령검색·조문조회를 제공한다.
저수준 호출/캐시/약칭해소는 이미 있는 resolver 계층(LawGoKrResolver)을 재사용한다
— 여기서 새 HTTP 경로를 만들지 않는다(재시도·캐시 정책 단일화).
"""

from __future__ import annotations

import re

from .client import _as_rows, _mst_of, _norm
from .models import LawSearchResult, LawText
from .resolver import LawGoKrResolver

__all__ = ["search_law", "get_law_text", "normalize_article_key"]

# '조'는 선택적 — 맨 숫자('5')도 제5조로 받는다. 항·호 표기는 뒤가 무시돼 조로 환원.
_ART_RE = re.compile(r"제?\s*(\d+)\s*조?(?:\s*의\s*(\d+))?")


def normalize_article_key(article: str) -> str:
    """조문 표기('제5조', '5', '제5조의2', '제5조제2항') → 조 단위 키('제5조'/'제5조의2').

    조문조회는 조(條) 단위로 본문을 돌려주므로 항·호는 조 키로 환원한다.
    """
    s = article.strip()
    m = _ART_RE.search(s)
    if not m:
        raise ValueError(f"조문 표기를 해석할 수 없습니다: {article!r} (예: '제5조', '제5조의2')")
    base = f"제{int(m.group(1))}조"
    if m.group(2):
        base += f"의{int(m.group(2))}"
    return base


def search_law(
    resolver: LawGoKrResolver,
    query: str,
    *,
    current_only: bool = False,
    limit: int | None = None,
) -> list[LawSearchResult]:
    """법령명·키워드로 법령을 검색한다.

    검색결과가 없으면 빈 리스트(예외 없음). `current_only=True` 면 현행만.
    약칭/부분명이면 정식명으로 자동 확장해 재검색한다(공식 약칭사전 재사용).
    """
    rows = _as_rows(resolver._search("law", query))
    if not rows:
        # 약칭/부분명일 수 있음 → resolver 의 해소 결과로 정식명 재검색.
        info = resolver.resolve(query)
        if info.current_name and _norm(info.current_name) != _norm(query):
            rows = _as_rows(resolver._search("law", info.current_name))

    out: list[LawSearchResult] = []
    for r in rows:
        status = (r.get("현행연혁코드") or "").strip()
        if current_only and status != "현행":
            continue
        out.append(
            LawSearchResult(
                law_id=str(r.get("법령ID") or ""),
                name=r.get("법령명한글") or "",
                status=status,
                enforce_date=r.get("시행일자") or "",
                abbr=(r.get("법령약칭명") or "").strip() or None,
                law_type=r.get("법종구분명") or "",
                mst=_mst_of(r),
                detail_link=r.get("법령상세링크") or "",
            )
        )
        if limit is not None and len(out) >= limit:
            break
    return out


def get_law_text(
    resolver: LawGoKrResolver,
    law: str,
    article: str | None = None,
) -> LawText:
    """현행 법령의 조문 본문을 가져온다.

    `article` 지정 시 해당 조문만(항·호 표기는 조 단위로 환원). 없으면 전문.
    약칭/부분명도 정식 현행명으로 해소해 조회한다.
    법령을 찾지 못하면 ValueError.
    """
    name = law
    arts = resolver.current_articles(name)
    if not arts:
        # 약칭/부분명 → 현행 정식명 해소 후 재시도.
        info = resolver.resolve(law)
        if info.current_name and _norm(info.current_name) != _norm(law):
            name = info.current_name
            arts = resolver.current_articles(name)
    if not arts:
        raise ValueError(f"현행 법령 「{law}」을(를) 찾지 못했습니다(법령명·약칭 확인).")

    requested = None
    if article is not None:
        key = normalize_article_key(article)
        body = arts.get(key)
        if body is None:
            raise ValueError(f"「{name}」에 조문 {key}이(가) 없습니다.")
        arts = {key: body}
        requested = key

    return LawText(name=name, articles=arts, requested_article=requested)
