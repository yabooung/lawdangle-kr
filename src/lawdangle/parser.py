"""① Parser — 인용 추출.

DESIGN.md §3 ①.
추출 단위: 「(법령명)」 제○조(의○)(제○항)(제○호)
"""

from __future__ import annotations

import re

from .models import Citation

# 「」 안 법령명 + 뒤따르는 조문번호 패턴.
# 법령명: 「」 사이 임의 문자(개행 제외). 조문: 제\d+조(의\d+)?(제\d+항)?(제\d+호)?
_CITATION_RE = re.compile(
    r"「(?P<law>[^」\n]+?)」"
    r"\s*"
    r"(?P<article>제\d+조(?:의\d+)?(?:\s*제\d+항)?(?:\s*제\d+호)?)?"
)

# 「」 안에 들어오지만 법령명이 아닌 것(고시명/별표명 등) 필터용 꼬리말.
# DESIGN.md §3 ① 주의 — 고시명/별표명 배제.
_NON_LAW_SUFFIX = ("별표", "별지", "서식", "고시", "공고", "훈령", "예규", "지침")


def _looks_like_law(name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    # "별표1", "고시 제2020-1호"처럼 꼬리에 번호가 붙어도 잡도록
    # 끝쪽 숫자/공백/제~호 표기를 떼고 비-법령 꼬리말 검사.
    stem = re.sub(r"[\s\d제\-호]+$", "", name)
    if stem.endswith(_NON_LAW_SUFFIX):
        return False
    return True


def _clean_article(article: str | None) -> str | None:
    if article is None:
        return None
    # 내부 공백 제거: "제17조 제2항" → "제17조제2항"
    return re.sub(r"\s+", "", article)


def parse_citations(text: str, *, citing_law: str = "", citing_article: str = "") -> list[Citation]:
    """법령 본문 문자열에서 인용 레코드를 추출한다.

    한 조문에 여러 인용 가능 → 리스트 반환.
    `citing_law`/`citing_article`은 인용하는 쪽 메타(있으면 채워 넘김).
    """
    out: list[Citation] = []
    for m in _CITATION_RE.finditer(text):
        law = m.group("law").strip()
        if not _looks_like_law(law):
            continue
        out.append(
            Citation(
                citing_law=citing_law,
                citing_article=citing_article,
                cited_law_name=law,
                cited_article=_clean_article(m.group("article")),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 조문번호 한글표기 ↔ API 코드 변환
# DESIGN.md §3 ① — 제5조제2항 ↔ 000500... (korean-law-mcp 변환 로직 참고)
# --------------------------------------------------------------------------- #

_ARTICLE_TOKEN_RE = re.compile(r"제(\d+)조(?:의(\d+))?")


def article_to_code(article: str) -> str | None:
    """제\\d+조(의\\d+) → 6자리 조문 코드.

    예) 제5조      → "000500"
        제5조의2   → "000502"
    항/호는 별도 필드이므로 여기선 조(條) 단위만 코드화.
    """
    m = _ARTICLE_TOKEN_RE.search(article)
    if not m:
        return None
    jo = int(m.group(1))
    ui = int(m.group(2)) if m.group(2) else 0
    return f"{jo:04d}{ui:02d}"
