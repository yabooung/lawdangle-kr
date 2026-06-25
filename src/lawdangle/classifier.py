"""③ Classifier — 5분류 (도구의 심장).

DESIGN.md §3 ③ 의사결정 트리 구현.
핵심 원칙: C/D/E는 자동 단정 금지 — 플래그만 달고 사람이 본다.
"""

from __future__ import annotations

import re

from .models import Category, Citation, Confidence, HistoryInfo, LawStatus, Result

_ART_KEY_RE = re.compile(r"(제\d+조(?:의\d+)?)")


def _article_key(article: str | None) -> str | None:
    """'제17조제2항' → 조(條) 단위 키 '제17조'."""
    if not article:
        return None
    m = _ART_KEY_RE.match(article)
    return m.group(1) if m else None


def _normalize_name(name: str) -> str:
    """법명 정규화 — 약칭/표기차(가운뎃점ㆍ, 띄어쓰기)를 개명으로 오판 방지.

    DESIGN.md §6 함정 1.
    """
    return name.replace("ㆍ", "").replace("·", "").replace(" ", "").strip()


def classify(citation: Citation, history: HistoryInfo) -> Result:
    """인용 레코드 + 연혁 → 5분류 판정.

    의사결정 트리(DESIGN.md §3 ③):
      1. 현행 유지? → 법명 동일? → 정상 / 개명(A)
      2. 폐지 → 후속법 수로 B / C / D·E 분기
    """
    cited_name = citation.cited_law_name
    status = history.status

    # --- 1. 현행 유지 ---------------------------------------------------- #
    if status == LawStatus.CURRENT:
        current = history.current_name or cited_name
        if _normalize_name(cited_name) == _normalize_name(current):
            # 정상 — 분류 대상 아님. category=None.
            return Result(
                citation=citation,
                history=history,
                category=None,
                confidence=Confidence.HIGH,
                note="현행 유지·법명 일치 (정상)",
            )
        # 현행이지만 인용 법명이 현행명과 다름 → 약칭/부분명/표기차 = A(법명만 교체)
        cause = {
            "alias": "약칭",
            "partial": "부분명(앞부분 생략)",
        }.get(history.name_form, "표기차/개명")
        return Result(
            citation=citation,
            history=history,
            category=Category.A,
            confidence=Confidence.HIGH,
            successor_suggestion=current,
            note=f"{cause}: 「{cited_name}」 → 현행 「{current}」 (풀네임 표기 권장)",
        )

    # --- 2. 개명(법인격 동일) → 조문 보존 여부로 A vs B 분기 ------------- #
    if status == LawStatus.RENAMED:
        current = history.current_name
        art_key = _article_key(citation.cited_article)

        # 인용 조문이 현행본에 살아있으면 깨끗한 개명(A: 법명만 교체).
        if art_key is None or not history.alive_articles or art_key in history.alive_articles:
            return Result(
                citation=citation,
                history=history,
                category=Category.A,
                confidence=Confidence.HIGH,
                successor_suggestion=current,
                note=f"단순 개명: 「{cited_name}」 → 「{current}」 (법명만 교체)",
            )

        # 법은 개명됐으나 인용 조문이 현행본에 없음(삭제/전부개정 재번호) → B.
        return Result(
            citation=citation,
            history=history,
            category=Category.B,
            confidence=Confidence.MEDIUM,
            successor_suggestion=current,
            flag=True,
            note=(
                f"개명+조문 이동: 「{cited_name}」→「{current}」(법인격 동일)이나 "
                f"인용 {art_key}이 현행본에 없음(삭제/재번호). 법명+조문 교체 필요 — "
                "--map 으로 대응 조문 확인 [수동]"
            ),
        )

    # --- 3. 폐지 → 후속법 분석 ------------------------------------------ #
    if status == LawStatus.REPEALED:
        n = len(history.successors)

        if n == 1:
            # 후속법 단일. 조문 대응이 깨질 수 있으므로(함정 2) 조문 교체 플래그.
            # 단정 자동: B. 단, 조문번호 변경 가능성은 note로 경고.
            return Result(
                citation=citation,
                history=history,
                category=Category.B,
                confidence=Confidence.MEDIUM,
                successor_suggestion=history.successors[0],
                flag=True,
                note=(
                    f"전부개정·이관: 제도가 「{history.successors[0]}」(으)로 승계. "
                    "법명+조문 교체 필요 — 조문번호 대응 확인할 것"
                ),
            )

        if n >= 2:
            # 후속법 여럿 → 분할 승계 C. 호 단위 수동 매핑 필수.
            return Result(
                citation=citation,
                history=history,
                category=Category.C,
                confidence=Confidence.MANUAL,
                successor_suggestion=", ".join(history.successors),
                flag=True,
                note=(
                    "분할 승계(1:N): 내용이 여러 법으로 분산. "
                    "호 단위 수동 매핑 필요 [수동]"
                ),
            )

        # n == 0: 확정 후속법 없음 → 폐지법 상세 산문 신호로 보강.
        # 자동으로 D/E를 단정하지 않는다 — 모두 manual_required(오탐 차단, §3③).

        if history.absorbed:
            # "일반회계로 통합/흡수" 등 → 후속'법'이 없고 자체 흡수 → D 강신호.
            note = "폐지·흡수통합: " + (history.repeal_reason or "타 회계/제도로 흡수")
            return Result(
                citation=citation,
                history=history,
                category=Category.D,
                confidence=Confidence.MANUAL,
                successor_suggestion=None,
                flag=True,
                note=note + " — 자체 완결(D) 유력, 수동 확인 [수동]",
            )

        if history.successor_candidates:
            # 후속법 후보(타법폐지 역추적/제개정이유) — 개수로 B(이관)/C(분할) 구분.
            cands = history.successor_candidates
            joined = ", ".join(cands)
            if len(cands) == 1:
                return Result(
                    citation=citation,
                    history=history,
                    category=Category.B,
                    confidence=Confidence.MEDIUM,
                    successor_suggestion=cands[0],
                    flag=True,
                    note=(
                        f"폐지·이관 후보: 「{cands[0]}」(으)로 이관 추정. "
                        "법명+조문 교체 — --map 으로 대응 조문 확인 [수동]"
                    ),
                )
            return Result(
                citation=citation,
                history=history,
                category=Category.C,
                confidence=Confidence.MANUAL,
                successor_suggestion=joined,
                flag=True,
                note=(
                    f"폐지·분할 승계 후보: 「{joined}」 — 내용이 여러 법으로 분산. "
                    "호 단위 수동 매핑 필요 [수동]"
                ),
            )

        # 신호 없음 → D(자체 완결) / E(효과 마비) 갈림. 기본 후보 D, 최종은 사람이.
        return Result(
            citation=citation,
            history=history,
            category=Category.D,
            confidence=Confidence.MANUAL,
            successor_suggestion=None,
            flag=True,
            note=(
                "폐지·후속법 없음: 자체 완결(D)인지 효과 마비(E)인지 수동 확인 필요. "
                "E일 경우 최우선 검토 [수동]"
            ),
        )

    # --- status UNKNOWN: 조회 실패 -------------------------------------- #
    return Result(
        citation=citation,
        history=history,
        category=None,
        confidence=Confidence.LOW,
        flag=True,
        note="연혁 조회 실패 — 대상 법령 상태 미확인 [수동]",
    )
