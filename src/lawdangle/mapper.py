"""조문 대응 반자동 매핑 — 옛 조문 ↔ 후속법 현행 조문.

DESIGN.md §2 B(이관·조문대응) / C(분할 승계) 보조.

⚠️ 이 모듈은 **제안(suggestion)** 만 만든다. 확정하지 않는다.
   설계 §6 함정 2: "후속법 단일이라고 무조건 B 아님 — 조문 대응이 깨지면 …".
   본문 유사도 순위는 사람이 최종 확인하기 위한 출발점이지 정답이 아니다.

동작:
  1. 옛(폐지) 법의 연혁을 시행일 내림차순으로 walk → '삭제'가 아닌 마지막
     실본문 조문 텍스트를 찾는다(조문이 폐지 전 이미 삭제된 경우 대비).
  2. 후속법의 현행 조문 본문을 모두 가져온다.
  3. 토큰 자카드 유사도로 후속 조문을 순위 매겨 top-k 제안.
  유사도가 전부 낮으면 → "대응 조문 불명(다른 후속법/분할 의심)" 신호.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Category, LawStatus, Result
from .resolver import LawGoKrResolver, is_deleted

# 의미 토큰: 한글 2자+ / 영문 / 숫자. 조사·한 글자 노이즈 제외.
_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z]{2,}|\d+")

# 본문엔 흔하지만 변별력 없는 토큰 — 유사도에서 제외.
_STOPWORDS = frozenset({
    "경우", "규정", "다음", "각호", "관한", "관하여", "대통령령", "에서", "으로",
    "위하여", "위한", "따른", "따라", "제외", "포함", "이내", "이상", "이하", "또는",
})


def tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text) if t not in _STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


@dataclass
class MappingCandidate:
    article: str        # 후속법 조문키 (예: 제10조)
    score: float        # 0~1 유사도
    snippet: str        # 후속 조문 본문 발췌


@dataclass
class MappingSuggestion:
    old_law: str
    old_article: str
    old_article_version: str | None  # 실본문을 찾은 시행일자
    old_snippet: str
    successor_law: str
    candidates: list[MappingCandidate]
    confident: bool      # 최상위 후보가 임계 이상이고 2위와 충분히 벌어졌나
    note: str

    @property
    def best(self) -> MappingCandidate | None:
        return self.candidates[0] if self.candidates else None


def rank_correspondence(
    old_text: str, successor_articles: dict[str, str], top_k: int = 3
) -> list[MappingCandidate]:
    """옛 조문 본문 vs 후속법 현행 조문들 → 유사도 순위 top-k."""
    ot = tokenize(old_text)
    scored = [
        MappingCandidate(article=k, score=round(jaccard(ot, tokenize(v)), 3), snippet=v[:80])
        for k, v in successor_articles.items()
        if v and not is_deleted(v)
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


def find_old_article_text(
    resolver: LawGoKrResolver, old_law: str, article_key: str
) -> tuple[str | None, str]:
    """옛 법 연혁을 거슬러 '삭제' 아닌 마지막 실본문을 찾는다(조 단위).

    returns (시행일자 or None, 본문텍스트). 못 찾으면 (None, "").
    """
    ver, text, _ = find_old_article_detailed(resolver, old_law, article_key, None)
    return ver, text


def find_old_article_detailed(
    resolver: LawGoKrResolver, old_law: str, article_key: str, hang: int | None
) -> tuple[str | None, str, str]:
    """옛 법 연혁을 거슬러 '삭제' 아닌 마지막 실본문 조 + (요청 시)항 텍스트.

    returns (시행일자, 조본문, 항본문). 항 미지정/없음이면 항본문은 "".
    """
    for row in resolver.versions(old_law):
        mst = row.get("법령일련번호")
        if not mst:
            continue
        detail = resolver.articles_detailed(str(mst))
        jo = detail.get(article_key)
        if jo and jo["text"] and not is_deleted(jo["text"]):
            hang_text = jo["hangs"].get(hang, "") if hang is not None else ""
            return row.get("시행일자"), jo["text"], hang_text
    return None, "", ""


# 최상위 후보를 '유력'으로 볼 임계값(보수적).
_CONFIDENT_MIN = 0.18
_CONFIDENT_GAP = 0.06


def suggest_mapping(
    resolver: LawGoKrResolver,
    old_law: str,
    old_article: str,
    successor_law: str,
    *,
    top_k: int = 3,
) -> MappingSuggestion:
    """옛(폐지) 법의 한 조문이 후속법의 어느 조문(+항)에 대응하는지 제안.

    old_article 예: '제17조제2항' → 조 단위로 후속 조를 찾고, 항이 있으면
    최상위 후속 조 안에서 항 단위까지 좁힌다(호 단위는 설계상 수동 — C).
    """
    # '제17조제2항제14호' → 조키 '제17조', 항정수 2
    m = re.match(r"(제\d+조(?:의\d+)?)", old_article)
    art_key = m.group(1) if m else old_article
    hm = re.search(r"제(\d+)항", old_article)
    hang = int(hm.group(1)) if hm else None

    ver, old_text, old_hang_text = find_old_article_detailed(
        resolver, old_law, art_key, hang
    )
    if not old_text:
        return MappingSuggestion(
            old_law, art_key, None, "", successor_law, [],
            confident=False,
            note=f"옛 법 「{old_law}」 {art_key} 실본문을 찾지 못함(연혁에 없음/계속 삭제 상태).",
        )

    succ_detail = resolver.current_articles_detailed(successor_law)
    if not succ_detail:
        return MappingSuggestion(
            old_law, art_key, ver, old_text[:80], successor_law, [],
            confident=False,
            note=f"후속법 「{successor_law}」 현행 조문을 가져오지 못함(법명 확인 필요).",
        )

    succ_flat = {k: v["text"] for k, v in succ_detail.items()}
    cands = rank_correspondence(old_text, succ_flat, top_k=top_k)

    # 항 단위 정밀화: 최상위 후속 조 안에서 옛 항 본문과 가장 유사한 항을 찾는다.
    hang_note = ""
    if cands and hang is not None and old_hang_text:
        best_hangs = succ_detail.get(cands[0].article, {}).get("hangs", {})
        if best_hangs:
            ot = tokenize(old_hang_text)
            ranked_h = sorted(
                ((n, jaccard(ot, tokenize(t))) for n, t in best_hangs.items()),
                key=lambda x: x[1], reverse=True,
            )
            if ranked_h and ranked_h[0][1] >= _CONFIDENT_MIN:
                hn = ranked_h[0][0]
                cands[0].article = f"{cands[0].article}제{hn}항"
                hang_note = f" (항 정밀화: 제{hn}항 유사도 {round(ranked_h[0][1], 3)})"

    confident = bool(
        cands
        and cands[0].score >= _CONFIDENT_MIN
        and (len(cands) < 2 or cands[0].score - cands[1].score >= _CONFIDENT_GAP)
    )
    if not cands or cands[0].score < _CONFIDENT_MIN:
        note = "대응 조문 불명 — 유사도 낮음(다른 후속법/분할 승계 의심). 수동 확인 필수."
    elif confident:
        note = f"유력 후보 {cands[0].article} (유사도 {cands[0].score}). 조문 대조 후 확정 — 수동."
    else:
        note = "복수 후보 경합 — 분할 승계(C) 가능. 호 단위 수동 매핑 필요."

    return MappingSuggestion(
        old_law, art_key, ver, old_text[:80], successor_law, cands,
        confident=confident, note=note + hang_note,
    )


def _norm_name(s: str) -> str:
    return s.replace("ㆍ", "").replace("·", "").replace(" ", "").strip()


def discover_successors(
    resolver: LawGoKrResolver,
    old_article_text: str,
    *,
    exclude: tuple[str, ...] = (),
    max_terms: int = 8,
    max_per_term: int = 6,
) -> list[str]:
    """옛 조문 본문의 특징 개념어로 현행 법령명을 검색해 후속법 후보를 발견한다.

    분할 이관처럼 '법 전체의 일반 승계자'가 아닌 **그 조항의 실제 후속법**을 찾는다.
    예) 「국가균형발전 특별법」§17 본문의 '산업위기대응특별지역' →
        「지역 산업위기 대응 및 지역경제 회복을 위한 특별법」.

    핵심 휴리스틱: 긴 복합명사(제도명)일수록, 그 이름으로 법령명을 쳤을 때
    결과가 적을수록(=그 제도를 '정의'하는 법) 점수가 높다.
    """
    ex = {_norm_name(e) for e in exclude}
    terms = sorted(
        {t for t in tokenize(old_article_text) if len(t) >= 5},
        key=len, reverse=True,
    )[:max_terms]
    scores: dict[str, float] = {}
    for term in terms:
        laws = [l for l in resolver.find_current_laws(term) if _norm_name(l) not in ex]
        if not laws or len(laws) > max_per_term:
            continue  # 너무 흔한 단어(=인용만 한 법 다수) → 버림
        for law in laws:
            scores[law] = scores.get(law, 0.0) + len(term) / len(laws)
    return sorted(scores, key=lambda k: scores[k], reverse=True)


def suggest_mapping_auto(
    resolver: LawGoKrResolver,
    old_law: str,
    old_article: str,
    *,
    candidate_laws: int = 3,
    top_k: int = 3,
) -> MappingSuggestion | None:
    """후속법을 모를 때: 본문 기반으로 후속법을 발견한 뒤 조문 대응까지 제안.

    옛 조문 본문 → 개념어로 현행법 발견 → 각 후보법에 매핑 → 최고 유사도 선택.
    """
    m = re.match(r"(제\d+조(?:의\d+)?)", old_article)
    art_key = m.group(1) if m else old_article
    hm = re.search(r"제(\d+)항", old_article)
    hang = int(hm.group(1)) if hm else None

    ver, old_text, _ = find_old_article_detailed(resolver, old_law, art_key, hang)
    if not old_text:
        return None

    succ_laws = discover_successors(resolver, old_text, exclude=(old_law,))
    best: MappingSuggestion | None = None
    for law in succ_laws[:candidate_laws]:
        s = suggest_mapping(resolver, old_law, old_article, law, top_k=top_k)
        if s.best and (best is None or (best.best and s.best.score > best.best.score)):
            best = s
    return best


def enrich_result(result: Result, resolver: LawGoKrResolver) -> Result:
    """분류 결과에 '후속법 + 구체 대응 조문' 제안을 덧붙인다(조문 단위 디테일).

    - 개명+조문이동(B): 같은 개명법 안에서 조문 매핑.
    - 이관(B)·분할(C): **본문 기반 후속법 자동 발견** + 조문 매핑(분할 이관도 자동).
    - A(깨끗한 개명)·D(흡수)·E·정상: 매핑 안 함(과잉 단정 방지).
    successor_suggestion / note 를 갱신해 반환(원본 객체 수정).
    """
    c = result.citation
    if not c.cited_article or result.category is None:
        return result

    s: MappingSuggestion | None = None
    if result.history.status == LawStatus.RENAMED and result.category == Category.B:
        # 개명법 안에서 조문이 이동/재번호 → 현행 개명본을 대상으로 매핑.
        if result.history.current_name:
            s = suggest_mapping(resolver, c.cited_law_name, c.cited_article,
                                result.history.current_name)
    elif result.category in (Category.B, Category.C):
        # 이관·분할 → 후속법을 본문으로 자동 발견한 뒤 매핑(분할 이관 자동 처리).
        s = suggest_mapping_auto(resolver, c.cited_law_name, c.cited_article)

    if s and s.best:
        tag = "유력" if s.confident else "후보"
        result.successor_suggestion = f"{s.successor_law} {s.best.article}"
        result.note += (
            f" | 조문제안({tag}): 「{s.successor_law}」 {s.best.article}"
            f"(유사도 {s.best.score})"
        )
    return result
