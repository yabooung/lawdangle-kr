"""법제처 OPEN API(law.go.kr DRF) 저수준 HTTP 클라이언트.

resolver / search 가 공유하는 호출 계층을 여기로 모은다.
- OC(이메일 ID 인증키), 타임아웃, 재시도(지수 백오프)
- HTML 에러페이지(간헐 장애·인증오류) 감지 → 조용한 빈응답 대신 명시적 예외
- lawSearch.do / lawService.do 얇은 래퍼

이전에는 resolver.LawGoKrResolver._get 에 묶여 있어 검색/조문조회 기능이
같은 재시도·캐시 정책을 공유하지 못했다. 이 모듈로 추출해 단일 경로로 만든다.
"""

from __future__ import annotations

import json
import re
import time

__all__ = ["LawClient", "LawApiError"]

BASE = "http://www.law.go.kr/DRF"


class LawApiError(RuntimeError):
    """법제처 API 호출 실패(네트워크·HTTP·HTML 에러페이지·모두 재시도 소진)."""


# --------------------------------------------------------------------------- #
# 응답 행 정규화 헬퍼 (resolver/search 공용)
# --------------------------------------------------------------------------- #


def _norm(name: str) -> str:
    """법명 비교용 정규화 — 가운뎃점/공백 차이 무시 (classifier와 동일 규칙)."""
    return name.replace("ㆍ", "").replace("·", "").replace(" ", "").strip()


def _as_rows(search_json: dict) -> list[dict]:
    """lawSearch.do 응답 → law 행 리스트. (1건이면 dict, 0건이면 키 없음)"""
    ls = search_json.get("LawSearch", search_json)
    rows = ls.get("law", [])
    if isinstance(rows, dict):
        return [rows]
    return rows or []


def _total_count(search_json: dict) -> int:
    """lawSearch.do 응답의 totalCnt — 페이징 종료 판단용. 미상 0."""
    ls = search_json.get("LawSearch", search_json)
    try:
        return int(ls.get("totalCnt") or 0)
    except (TypeError, ValueError):
        return 0


def _exact(rows: list[dict], name: str) -> list[dict]:
    target = _norm(name)
    return [r for r in rows if _norm(r.get("법령명한글", "")) == target]


def _latest(rows: list[dict]) -> dict:
    """시행일자(YYYYMMDD) 최신 행."""
    return max(rows, key=lambda r: r.get("시행일자", "") or "")


def _mst_of(row: dict) -> str | None:
    """검색행에서 상세조회용 MST(법령일련번호) 추출."""
    mst = row.get("법령일련번호")
    if mst:
        return str(mst)
    link = row.get("법령상세링크", "")
    m = re.search(r"MST=(\d+)", link)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# HTTP 클라이언트
# --------------------------------------------------------------------------- #


class LawClient:
    """법제처 DRF API 호출기 — 검색/상세 공용.

    OC(이메일 ID 인증키) 필요: https://open.law.go.kr 발급.
    resolver/search 가 이 인스턴스를 주입받아 같은 재시도 정책을 쓴다.
    """

    BASE = BASE

    def __init__(self, oc: str, *, timeout: int = 10):
        self.oc = oc
        self.timeout = timeout

    # 페이지 크기 — DRF 기본 20은 짧은 법명('상법')이 부분문자열 매칭('보상…법')에
    # 밀려 첫 페이지에서 정확일치가 누락된다(2026-07-16 실측: '상법' 56건 중 후순위).
    PAGE_SIZE = 100

    def search(self, target: str, query: str, *, page: int | None = None) -> dict:
        """lawSearch.do — 법령명/키워드 검색 (display=PAGE_SIZE, page 지정 가능)."""
        params = {"target": target, "query": query, "display": self.PAGE_SIZE}
        if page is not None:
            params["page"] = page
        return self.get("lawSearch", params)

    def search_by_id(self, target: str, law_id: str) -> dict:
        """lawSearch.do — 법령ID로 검색(현행 생존/개명 판정용)."""
        return self.get("lawSearch", {"target": target, "ID": law_id})

    def service(self, target: str, mst: str) -> dict:
        """lawService.do — MST(법령일련번호)로 상세(조문/부칙) 조회."""
        return self.get("lawService", {"target": target, "MST": mst})

    def get(self, endpoint: str, extra: dict, *, retries: int = 2) -> dict:
        """DRF 엔드포인트 GET → JSON dict. 실패 시 LawApiError.

        - HTTP/네트워크 오류: 지수 백오프로 재시도 후 예외.
        - 200이지만 HTML(에러페이지): 조용히 빈응답 처리하면 '결과 없음'으로
          오인되므로 감지해 재시도 대상으로 던진다(간헐 장애 대비).
        - 200 + 빈 본문/파싱불가: 정상적인 '0건'일 수 있어 빈 dict 반환.
        """
        import requests  # 지연 임포트 — 오프라인 경로(fixture)에선 불필요

        params = {"OC": self.oc, "type": "JSON", **extra}
        url = f"{self.BASE}/{endpoint}.do"
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                if _looks_like_html(resp):
                    raise LawApiError(
                        f"법제처 API가 JSON 대신 HTML을 반환({endpoint}). "
                        "OC 키/파라미터 오류 또는 서버 일시장애일 수 있음."
                    )
                try:
                    return resp.json()
                except json.JSONDecodeError:
                    return {}  # 정상 0건/빈응답 — 예외 아님
            except (requests.RequestException, LawApiError) as e:
                last_err = e
                if attempt < retries:
                    time.sleep(0.5 * (attempt + 1))  # 0.5s, 1.0s 백오프
        raise LawApiError(f"법제처 API 호출 실패({endpoint}): {last_err}") from last_err


def _looks_like_html(resp) -> bool:
    """응답이 JSON이 아니라 HTML 에러페이지인가."""
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "html" in ctype:
        return True
    head = resp.text[:256].lstrip().lower()
    return head.startswith("<!doctype html") or head.startswith("<html")
