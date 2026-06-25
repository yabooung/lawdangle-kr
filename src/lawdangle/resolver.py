"""② History Resolver — 법제처 OPEN API 연혁 조회 + 캐시.

DESIGN.md §3 ② / §5 2번 — 전체의 급소.

라이브 API 확인 결과(2026-06, OC 인증 실응답으로 확정):

  • 현행 판정:  target=law 로 법령명 정확매칭 → 있으면 현행.
  • 폐지/연혁 판정:  target=eflaw(시행일법령)에 과거·폐지본이 누적.
      최신 `시행일자` 행의 `제개정구분명` 이 "폐지"/"타법폐지" → 폐지.
      `현행연혁코드` = "현행" | "연혁" 보조 신호.
  • 확정 필드명:  법령명한글 / 제개정구분명 / 현행연혁코드 / 시행일자 /
                  법령ID / 법령약칭명 / 법령상세링크.

  ⚠️ 후속·대체법(successor)은 *검색* API 응답엔 단일 필드로 없다.
     (lsStmd/oldAndNew 등 체계도 target도 법령명 쿼리론 0건)
     하지만 폐지법 *상세*(lawService.do)의 부칙·제개정이유 **산문**에는 있다:
       "…그 재산 등을 일반회계로 통합운영하려는 것임" → 흡수(D)
       "「○○법」으로 이관/통합" → 후속법 후보(B/C)
     → resolver가 상세를 한 번 더 긁어 successor_candidates / absorbed 신호를
       추출한다. 단 '후보'이지 확정이 아니므로 classifier는 여전히 수동 플래그를
       유지한다(§3 ③ — C/D/E 자동 단정 금지, 오탐 차단).
     함정: 부칙 "다른 법률의 개정"에 나오는 법은 후속법이 아니라 부수 개정 →
           후보에서 제외(제개정이유 산문만 후보 소스로 사용).

오프라인/회귀는 FixtureResolver 로 동일 인터페이스를 만족시킨다.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Protocol

from .models import HistoryInfo, LawStatus

# 같은 법령 반복 조회가 많음 → law명 기준 캐시(DESIGN: TTL 24h 권장).
_CACHE_TTL_SEC = 24 * 60 * 60

# 명시적 폐지 신호 (제개정구분명).
_REPEAL_TOKENS = ("폐지",)  # "폐지", "타법폐지", "폐지제정" 모두 부분일치


class Resolver(Protocol):
    """인용 대상 법령명 → 현재 상태/연혁."""

    def resolve(self, cited_law_name: str) -> HistoryInfo: ...


# --------------------------------------------------------------------------- #
# 정규화 헬퍼
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


# 흡수 신호 — 후속 '법' 없이 회계/제도로 흡수(특별회계→일반회계)되는 D 강신호.
# generic "통합"은 너무 흔해 오탐 → '일반회계' 흡수로 한정(보수적).
_ABSORB_TOKENS = ("일반회계",)

# 후속법 후보로 쓸 만한 이관/승계 동사(이 단어가 「법」 근처에 있으면 후보 가중).
_TRANSFER_TOKENS = ("이관", "승계", "통합", "대체", "이전")

_BRACKET_RE = re.compile(r"「([^」\n]+?)」")

# 후속법 후보로 인정할 법령명 꼬리말(슬로건/인용구 노이즈 배제).
_LAW_NAME_SUFFIX = ("법", "법률", "특별법", "특례법", "기본법", "령", "규칙", "조례", "규정")


def _flatten_text(node) -> str:
    """법제처 상세 JSON의 중첩 리스트/문자열을 평탄화해 한 덩어리 텍스트로."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(_flatten_text(x) for x in node)
    if isinstance(node, dict):
        return " ".join(_flatten_text(v) for v in node.values())
    return ""


def _content_text(node) -> str:
    """노드에서 '~내용'/'~제목' 키 값만 모아 한 덩어리로 (메타 번호 제외)."""
    parts: list[str] = []

    def rec(n):
        if isinstance(n, dict):
            for k, v in n.items():
                if isinstance(v, (dict, list)):
                    rec(v)
                elif isinstance(v, str) and ("내용" in k or "제목" in k):
                    parts.append(v)
        elif isinstance(n, list):
            for x in n:
                rec(x)

    rec(node)
    return " ".join(parts)


def _article_key(jo: dict) -> str | None:
    no = jo.get("조문번호")
    if not no:
        return None
    try:
        base = f"제{int(no)}조"
    except (TypeError, ValueError):
        return None
    branch = jo.get("조문가지번호") or ""
    if branch and branch != "0":
        base += f"의{int(branch)}"
    return base


def extract_articles(detail: dict) -> dict[str, str]:
    """lawService.do 상세 → {조문키: 본문텍스트}. 조문내용+항+호 포함."""
    law = detail.get("법령", detail)
    jos = law.get("조문", {}).get("조문단위", [])
    if isinstance(jos, dict):
        jos = [jos]
    out: dict[str, str] = {}
    for jo in jos:
        key = _article_key(jo)
        if key:
            out[key] = _content_text(jo).strip()
    return out


# 항번호 원문자(①②③…) ↔ 정수.
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def hang_num(label: str) -> int | None:
    """항번호 라벨('②' 또는 '2') → 정수. 없으면 None."""
    if not label:
        return None
    label = label.strip()
    for ch in label:
        if ch in _CIRCLED:
            return _CIRCLED.index(ch) + 1
    digits = re.sub(r"\D", "", label)
    return int(digits) if digits else None


def extract_articles_detailed(detail: dict) -> dict[str, dict]:
    """lawService.do 상세 → {조문키: {"text": 조본문, "hangs": {항정수: 항본문}}}.

    조 단위 매핑(text) + 항 단위 정밀화(hangs)에 함께 쓴다.
    """
    law = detail.get("법령", detail)
    jos = law.get("조문", {}).get("조문단위", [])
    if isinstance(jos, dict):
        jos = [jos]
    out: dict[str, dict] = {}
    for jo in jos:
        key = _article_key(jo)
        if not key:
            continue
        hangs: dict[int, str] = {}
        hl = jo.get("항", [])
        if isinstance(hl, dict):
            hl = [hl]
        for h in hl:
            n = hang_num(h.get("항번호", ""))
            if n is not None:
                hangs[n] = _content_text(h).strip()
        out[key] = {"text": _content_text(jo).strip(), "hangs": hangs}
    return out


def is_deleted(text: str) -> bool:
    """조문 본문이 '삭제'(예: '제17조 삭제 <2021.8.17>')인가."""
    return "삭제 <" in text[:25] or text.strip().endswith("삭제")


# 타법 부칙 헤더 "부칙(폐지시킨 법명) <제○호,날짜>" → 폐지시킨(=후속) 법명.
_OTHER_BU_HEADER_RE = re.compile(r"부칙\(([^)]+)\)\s*<")


def _extract_abolisher(law: dict, self_name: str) -> str | None:
    """타법폐지일 때 '폐지시킨 법'(=후속법)을 부칙 헤더에서 역추적.

    타법폐지본의 부칙은 폐지를 단행한 법의 부칙이며, 헤더가 그 법명을 담는다.
    그 부칙이 실제로 self를 폐지했는지("…「self」…폐지") 확인해 오추출 방지.
    """
    gubun = (law.get("기본정보", {}) or {}).get("제개정구분", "")
    if "타법폐지" not in gubun:
        return None
    bu = (law.get("부칙", {}) or {}).get("부칙단위", {})
    bu_list = [bu] if isinstance(bu, dict) else bu
    self_norm = _norm(self_name)
    for b in bu_list:
        text = _flatten_text(b)
        if "폐지" not in text:
            continue
        # 이 부칙이 self를 폐지했는지 확인
        if self_norm not in _norm(text):
            continue
        m = _OTHER_BU_HEADER_RE.search(text)
        if m:
            name = m.group(1).strip()
            if name.endswith(_LAW_NAME_SUFFIX) and _norm(name) != self_norm:
                return name
    return None


def parse_repeal_detail(detail: dict, self_name: str) -> tuple[list[str], bool, str]:
    """폐지법 상세(lawService.do) → (후속법 후보, 흡수여부, 제개정이유 발췌).

    후보 소스(우선순위):
      ① 타법폐지 부칙 헤더의 '폐지시킨 법'(역추적, 가장 신뢰)
      ② 제개정이유 산문의 「법령명」 (부칙 '다른 법률의 개정'은 부수개정이라 제외)
    """
    law = detail.get("법령", detail)
    reason = _flatten_text(law.get("제개정이유", "")).strip()

    candidates: list[str] = []
    self_norm = _norm(self_name)

    # ① 타법폐지 역추적 — 폐지시킨 법을 최우선 후보로.
    abolisher = _extract_abolisher(law, self_name)
    if abolisher:
        candidates.append(abolisher)

    # ② 제개정이유 산문.
    for name in _BRACKET_RE.findall(reason):
        n = name.strip()
        if not n.endswith(_LAW_NAME_SUFFIX):
            continue  # 「선계획 후개발」 같은 슬로건/인용구 배제
        if _norm(n) != self_norm and n not in candidates:
            candidates.append(n)

    absorbed = any(tok in reason for tok in _ABSORB_TOKENS) and not candidates
    excerpt = re.sub(r"\s+", " ", reason)[:200]
    return candidates, absorbed, excerpt


# --------------------------------------------------------------------------- #
# fixture(합성) raw → HistoryInfo
# --------------------------------------------------------------------------- #

_FIXTURE_STATUS_MAP = {
    "현행": LawStatus.CURRENT,
    "폐지": LawStatus.REPEALED,
    "타법폐지": LawStatus.REPEALED,
    "개명": LawStatus.RENAMED,
}


def _normalize_fixture(raw: dict) -> HistoryInfo:
    """FixtureResolver용 — 합성 raw({법령상태, 후속법령, ...}) → HistoryInfo.

    fixture는 '사람이 후속법까지 채워 넣은' 정비 후 데이터를 표현한다.
    """
    status = _FIXTURE_STATUS_MAP.get((raw.get("법령상태") or "").strip(), LawStatus.UNKNOWN)
    successors = raw.get("후속법령") or []
    if isinstance(successors, str):
        successors = [successors]
    return HistoryInfo(
        status=status,
        current_name=raw.get("현행법령명") or raw.get("법령명한글"),
        successors=list(successors),
        raw=raw,
    )


# --------------------------------------------------------------------------- #
# 법제처 OPEN API resolver (라이브)
# --------------------------------------------------------------------------- #


class LawGoKrResolver:
    """법제처 OPEN API(law.go.kr DRF) 기반 resolver.

    OC(이메일 ID 인증키) 필요: https://open.law.go.kr 발급.
    상태 판정(현행/폐지)까지 자동. 후속법은 검색 API로 불가 → 수동 플래그.
    """

    BASE = "http://www.law.go.kr/DRF"

    def __init__(
        self,
        oc: str,
        *,
        cache_ttl: int = _CACHE_TTL_SEC,
        timeout: int = 10,
        enrich: bool = True,
    ):
        self.oc = oc
        self.timeout = timeout
        self.enrich = enrich  # 폐지법 상세까지 긁어 후보/흡수신호 보강
        self._cache: dict[str, tuple[float, HistoryInfo]] = {}
        self._cache_ttl = cache_ttl
        self._abbr_map: dict[str, str] | None = None  # 공식 약칭사전(lazy)

    def resolve(self, cited_law_name: str) -> HistoryInfo:
        cached = self._cache.get(cited_law_name)
        if cached and (time.time() - cached[0]) < self._cache_ttl:
            return cached[1]

        info = self._lookup(cited_law_name)
        self._cache[cited_law_name] = (time.time(), info)
        return info

    def _lookup(self, name: str) -> HistoryInfo:
        # 1. 현행법령에서 정확매칭?
        cur = _exact(_as_rows(self._search("law", name)), name)
        if cur:
            row = _latest(cur)
            return HistoryInfo(
                status=LawStatus.CURRENT,
                current_name=row.get("법령명한글"),
                successors=[],
                raw=row,
            )

        # 2. 현행에 없음 → 연혁(시행일법령)에서 폐지/개명 확인.
        hist = _exact(_as_rows(self._search("eflaw", name)), name)
        if not hist:
            # 실명 매칭 실패 → 약칭/부분명 해소 시도(공식 약칭사전 + 부분일치).
            alias = self._resolve_alias(name)
            if alias:
                return alias
            # 그래도 없음 → 미확인(오타/별표명 등).
            return HistoryInfo(status=LawStatus.UNKNOWN, raw={"query": name})

        latest = _latest(hist)
        law_id = latest.get("법령ID")

        # 2a. 개명(A) 판정 — 법령ID 연속성.
        #   옛 이름은 현행에 없지만 같은 법령ID가 현행에 '다른 이름'으로 살아있으면
        #   = 법인격 동일·제명변경 = 개명(A). (라이브 확인: lawSearch target=law&ID=)
        if law_id:
            alive = [
                r for r in _as_rows(self._search_by_id("law", law_id))
                if (r.get("현행연혁코드") or "").strip() == "현행"
            ]
            if alive:
                new_name = alive[0].get("법령명한글")
                renamed = _norm(new_name or "") != _norm(name)
                info = HistoryInfo(
                    status=LawStatus.RENAMED if renamed else LawStatus.CURRENT,
                    current_name=new_name,
                    name_form="rename" if renamed else "exact",
                    raw={**latest, "_current_id_row": alive[0]},
                )
                # 개명이면 현행본의 살아있는 조(條) 집합을 채워, classifier가
                # 인용 조문 보존 여부(A vs B-재번호)를 판정하게 한다.
                if renamed and self.enrich:
                    mst = _mst_of(alive[0])
                    if mst:
                        arts = self.articles(mst)
                        info.alive_articles = {
                            k for k, v in arts.items() if v and not is_deleted(v)
                        }
                return info

        # 2b. 법령ID가 현행에 없음 → 진짜 폐지(REPEALED).
        gubun = latest.get("제개정구분명", "")
        is_repeal = any(tok in gubun for tok in _REPEAL_TOKENS)
        info = HistoryInfo(
            status=LawStatus.REPEALED,
            current_name=None,
            successors=[],  # 검색 API로는 후속법 미상 → classifier가 수동 플래그
            raw={**latest, "_repeal_explicit": is_repeal},
        )
        # 폐지법 상세 산문에서 후속법 후보/흡수 신호 보강(명시 폐지일 때만 — 노이즈 차단).
        if self.enrich and is_repeal:
            mst = _mst_of(latest)
            if mst:
                detail = self._service("law", mst)
                cand, absorbed, reason = parse_repeal_detail(detail, name)
                info.successor_candidates = cand
                info.absorbed = absorbed
                info.repeal_reason = reason
        return info

    # --- 약칭/부분명 해소 ------------------------------------------------- #

    def _abbr(self) -> dict[str, str]:
        """공식 약칭사전 {정규화약칭: 법령명} — lazy 1회 로드(lsAbrv).

        lsAbrv 행은 현행/시행예정/연혁 혼재 → 현행 우선으로 채운다(이름은 동일).
        """
        if self._abbr_map is None:
            self._abbr_map = {}
            rows = _as_rows(self._get("lawSearch", {"target": "lsAbrv"}))
            order = {"현행": 0, "시행예정": 1, "연혁": 2}
            rows.sort(key=lambda r: order.get((r.get("현행연혁코드") or "").strip(), 3))
            for r in rows:
                ab = (r.get("법령약칭명") or "").strip()
                if ab:
                    self._abbr_map.setdefault(_norm(ab), r.get("법령명한글"))
        return self._abbr_map

    def _partial_current(self, name: str) -> str | None:
        """부분명(앞부분 생략) → 현행 풀네임. official.endswith(cited) 보수 매칭."""
        nn = _norm(name)
        if len(nn) < 8:  # 너무 짧으면 오매칭 위험 → 포기
            return None
        rows = _as_rows(self._search("law", name))
        cands = [
            r for r in rows
            if (r.get("현행연혁코드") or "").strip() == "현행"
            and _norm(r.get("법령명한글", "")).endswith(nn)
            and _norm(r.get("법령명한글", "")) != nn
        ]
        if "시행령" not in name and "시행규칙" not in name:
            cands = [r for r in cands
                     if not r.get("법령명한글", "").endswith(("시행령", "시행규칙"))]
        if not cands:
            return None
        cands.sort(key=lambda r: len(r.get("법령명한글", "")))  # 가장 구체(짧은) 우선
        return cands[0].get("법령명한글")

    def _resolve_alias(self, name: str) -> HistoryInfo | None:
        """공식 약칭 → 풀네임, 없으면 부분명 → 풀네임. 현행이면 CURRENT 반환."""
        canonical = self._abbr().get(_norm(name))
        form = "alias"
        if not canonical:
            canonical = self._partial_current(name)
            form = "partial"
        if not canonical:
            return None
        # canonical 은 약칭사전/부분일치 모두 '현행' 행에서 왔으므로 현행으로 본다.
        return HistoryInfo(
            status=LawStatus.CURRENT,
            current_name=canonical,
            name_form=form,
            raw={"query": name, "resolved": canonical},
        )

    # --- 조문/버전 조회 (mapper.py 가 쓰는 빌딩블록) ----------------------- #

    def versions(self, name: str) -> list[dict]:
        """eflaw 연혁 행 — 정확매칭, 시행일자 내림차순."""
        rows = _exact(_as_rows(self._search("eflaw", name)), name)
        rows.sort(key=lambda r: r.get("시행일자", "") or "", reverse=True)
        return rows

    def articles(self, mst: str) -> dict[str, str]:
        """특정 버전(MST)의 조문 본문 맵 {조문키: 내용텍스트}.

        target=law 는 과거본 MST도 조회된다(라이브 확인). 조문내용+항내용+호내용.
        """
        return extract_articles(self._service("law", mst))

    def current_articles(self, name: str) -> dict[str, str]:
        """현행 법령명 → 현행 조문 본문 맵. 없으면 빈 dict."""
        cur = _exact(_as_rows(self._search("law", name)), name)
        if not cur:
            return {}
        mst = _mst_of(_latest(cur))
        return self.articles(mst) if mst else {}

    def articles_detailed(self, mst: str) -> dict[str, dict]:
        """특정 버전(MST)의 조문 상세 맵 {조키: {text, hangs}}."""
        return extract_articles_detailed(self._service("law", mst))

    def current_articles_detailed(self, name: str) -> dict[str, dict]:
        """현행 법령명 → 현행 조문 상세 맵(조본문+항). 없으면 빈 dict."""
        cur = _exact(_as_rows(self._search("law", name)), name)
        if not cur:
            return {}
        mst = _mst_of(_latest(cur))
        return self.articles_detailed(mst) if mst else {}

    def find_current_laws(self, query: str) -> list[str]:
        """법령명 부분검색 → 현행 '법률'명 리스트(시행령·시행규칙 제외, 중복 제거).

        분할 이관 후속법 발견(content discovery)에 쓴다.
        """
        out: list[str] = []
        for r in _as_rows(self._search("law", query)):
            if (r.get("현행연혁코드") or "").strip() != "현행":
                continue
            nm = r.get("법령명한글", "")
            if not nm or nm.endswith(("시행령", "시행규칙")):
                continue
            if nm not in out:
                out.append(nm)
        return out

    def _search(self, target: str, query: str) -> dict:
        return self._get("lawSearch", {"target": target, "query": query})

    def _search_by_id(self, target: str, law_id: str) -> dict:
        """법령ID로 검색 — 현행 생존 여부/현행명 확인용(개명 판정)."""
        return self._get("lawSearch", {"target": target, "ID": law_id})

    def _service(self, target: str, mst: str) -> dict:
        return self._get("lawService", {"target": target, "MST": mst})

    def _get(self, endpoint: str, extra: dict, *, retries: int = 2) -> dict:
        import requests  # 지연 임포트 — 오프라인 경로에선 불필요

        params = {"OC": self.oc, "type": "JSON", **extra}
        url = f"{self.BASE}/{endpoint}.do"
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                try:
                    return resp.json()
                except json.JSONDecodeError:
                    return {}
            except requests.RequestException as e:  # 네트워크/HTTP 일시 오류 → 재시도
                last_err = e
                if attempt < retries:
                    time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"법제처 API 호출 실패({endpoint}): {last_err}") from last_err


# --------------------------------------------------------------------------- #
# Fixture resolver (오프라인/회귀 테스트)
# --------------------------------------------------------------------------- #


class FixtureResolver:
    """법령명 → HistoryInfo 매핑을 미리 박아둔 오프라인 resolver.

    test/fixtures/*.json 또는 직접 넘긴 dict로 구동.
    fixture는 후속법까지 채워진 '정비 후' 데이터 → 회귀(B/D)와 데모에 사용.
    """

    def __init__(self, mapping: dict[str, HistoryInfo]):
        self._mapping = mapping

    @classmethod
    def from_files(cls, *paths: str | Path) -> "FixtureResolver":
        mapping: dict[str, HistoryInfo] = {}
        for p in paths:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            for entry in data.get("history", []):
                mapping[entry["cited_law_name"]] = _normalize_fixture(entry["raw"])
        return cls(mapping)

    def resolve(self, cited_law_name: str) -> HistoryInfo:
        return self._mapping.get(
            cited_law_name,
            HistoryInfo(status=LawStatus.UNKNOWN, raw={"query": cited_law_name}),
        )
