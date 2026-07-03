"""법령 검색·조문 조회 공개 API (Phase 1).

로컬 라이브러리로 법령검색·조문조회를 제공한다. 저수준 호출/캐시/약칭해소는
이미 있는 resolver 계층(LawGoKrResolver)을 재사용한다 — 새 HTTP 경로를 만들지
않는다(재시도·캐시 정책 단일화).
"""

from __future__ import annotations

import re

from .client import _as_rows, _exact, _latest, _mst_of, _norm
from .models import LawSearchResult, LawText
from .resolver import LawGoKrResolver

__all__ = ["search_law", "get_law_text", "normalize_article_key"]

# 조 명시(제N조[의M]) — 뒤의 항·호(제2항 등)는 조 단위로 환원되어 무시된다.
_ART_RE = re.compile(r"^제?\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
# 맨 숫자만(5) → 제5조. 장/절/항/호 등 다른 단위 표기는 조로 오독하지 않도록 거부.
_BARE_NUM_RE = re.compile(r"^\s*(\d+)\s*$")


def normalize_article_key(article: str) -> str:
    """조문 표기 → 조 단위 키('제5조'/'제5조의2').

    허용: '제5조', '제5조의2', '제5조제2항'(→제5조), '5'(→제5조).
    거부: '제3장'·'제5호'·'제2항' 처럼 조가 아닌 단위가 주 표기인 경우(오독 방지).
    """
    s = article.strip()
    m = _ART_RE.match(s)
    if m:
        base = f"제{int(m.group(1))}조"
        if m.group(2):
            base += f"의{int(m.group(2))}"
        return base
    bare = _BARE_NUM_RE.match(s)
    if bare:
        return f"제{int(bare.group(1))}조"
    raise ValueError(
        f"조문 표기를 해석할 수 없습니다: {article!r} "
        "(예: '제5조', '제5조의2', '5'). 장·절·항·호는 조 단위로 지정하세요."
    )


def _relevance_key(name: str, query_norm: str):
    """정확일치 > 접두일치 > 부분일치 > 그 외, 그 안에서 짧은 이름 우선."""
    nn = _norm(name)
    if nn == query_norm:
        rel = 0
    elif nn.startswith(query_norm):
        rel = 1
    elif query_norm in nn:
        rel = 2
    else:
        rel = 3
    return rel, len(name)


def search_law(
    resolver: LawGoKrResolver,
    query: str,
    *,
    current_only: bool = False,
    limit: int | None = None,
) -> list[LawSearchResult]:
    """법령명·키워드로 법령을 검색한다(관련도 정렬).

    결과 없으면 빈 리스트(예외 없음). `current_only=True` 면 현행만.
    약칭/부분명이면 정식 현행명으로 자동 확장해 재검색한다.
    법제처 검색은 부분일치라(예: '민법'→'난민법' 포함) 정확·접두 일치를 앞에 둔다.
    """
    rows = _as_rows(resolver._search("law", query))
    if not rows:
        info = resolver.resolve(query)
        if info.current_name and _norm(info.current_name) != _norm(query):
            rows = _as_rows(resolver._search("law", info.current_name))

    results: list[LawSearchResult] = []
    for r in rows:
        status = (r.get("현행연혁코드") or "").strip()
        if current_only and status != "현행":
            continue
        results.append(
            LawSearchResult(
                law_id=str(r.get("법령ID") or ""),
                name=r.get("법령명한글") or "",
                status=status,
                enforce_date=r.get("시행일자") or "",
                abbr=(r.get("법령약칭명") or "").strip() or None,
                law_type=r.get("법령구분명") or "",
                mst=_mst_of(r),
                detail_link=r.get("법령상세링크") or "",
            )
        )

    qn = _norm(query)
    # 관련도 우선, 그 안에서 현행 우선.
    results.sort(key=lambda x: (_relevance_key(x.name, qn), 0 if x.is_current else 1))
    return results[:limit] if limit is not None else results


def _current_row(resolver: LawGoKrResolver, name: str) -> dict | None:
    """현행 법령명 정확매칭 → 최신 시행본 행. 없으면 None."""
    rows = _exact(_as_rows(resolver._search("law", name)), name)
    return _latest(rows) if rows else None


def get_law_text(
    resolver: LawGoKrResolver,
    law: str,
    article: str | None = None,
) -> LawText:
    """현행 법령의 조문 본문을 가져온다.

    `article` 지정 시 해당 조문만(항·호 표기는 조 단위로 환원). 없으면 전문.
    약칭/부분명도 정식 현행명으로 해소해 조회한다. 못 찾으면 ValueError.
    """
    name = law
    row = _current_row(resolver, name)
    if row is None:
        # 약칭/부분명 → 현행 정식명 해소 후 재시도.
        info = resolver.resolve(law)
        if info.current_name and _norm(info.current_name) != _norm(law):
            name = info.current_name
            row = _current_row(resolver, name)
    if row is None:
        raise ValueError(f"현행 법령 「{law}」을(를) 찾지 못했습니다(법령명·약칭 확인).")

    mst = _mst_of(row)
    arts = resolver.articles(mst) if mst else {}
    if not arts:
        raise ValueError(f"「{name}」의 조문을 가져오지 못했습니다(상세 조회 실패).")

    requested = None
    if article is not None:
        key = normalize_article_key(article)
        body = arts.get(key)
        if body is None:
            raise ValueError(f"「{name}」에 조문 {key}이(가) 없습니다.")
        arts = {key: body}
        requested = key

    return LawText(
        name=row.get("법령명한글") or name,
        articles=arts,
        law_id=str(row.get("법령ID") or "") or None,
        enforce_date=row.get("시행일자") or None,
        requested_article=requested,
    )
