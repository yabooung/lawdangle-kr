"""데이터 모델 — Citation, HistoryInfo, Result.

DESIGN.md §4 "데이터 모델" 스케치를 고정한 것.
나머지 모듈(parser/resolver/classifier/report)이 전부 여기에 맞춰 붙는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Category(Enum):
    """5분류 (도구의 심장). DESIGN.md §2."""

    A = "rename"            # 단순 개명           — 법명만 교체, 심각성 5(낮음)
    B = "transfer_mapped"   # 전부개정·이관(조문 대응) — 법명+조문 교체, 심각성 4
    C = "split_succession"  # 분할 승계(1:N)       — 호 단위 수동 매핑, 심각성 2
    D = "obsolete"          # 사문화(전제 소멸)     — 인용부 삭제·재구성, 심각성 3
    E = "dangling"          # 순수 폐지(빈 참조)    — 입법 보완, 심각성 1(최상)

    @property
    def severity(self) -> int:
        """제보/정비 우선순위. 1이 가장 심각(E), 5가 가장 경미(A).

        심각성 순위: E > C > D > B > A.
        """
        return {"E": 1, "C": 2, "D": 3, "B": 4, "A": 5}[self.name]


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual_required"


class LawStatus(Enum):
    """인용 대상 법령의 현재 상태 (resolver가 채움).

    실제 법제처 API 응답의 `법령상태`/`제정·개정구분` 필드를
    이 enum으로 정규화한다. // TODO: 필드 매핑은 resolver.py 참조.
    """

    CURRENT = "current"      # 현행
    REPEALED = "repealed"    # 폐지(순수 폐지/타법폐지)
    RENAMED = "renamed"      # 개명(법인격 동일, 내용 연속)
    UNKNOWN = "unknown"      # 조회 실패/미확인


@dataclass
class Citation:
    """① Parser 출력 — 인용 레코드 1건."""

    citing_law: str            # 인용하는 쪽 법령명
    citing_article: str        # 인용하는 쪽 조문 (예: 제13조제1항제14호)
    cited_law_name: str        # 인용당하는 법령명 (「」 안)
    cited_article: str | None  # 인용당하는 조문 (예: 제17조제2항), 없을 수 있음


@dataclass
class HistoryInfo:
    """② History Resolver 출력 — 인용 대상의 연혁 정보.

    A vs (B/C/D/E)를 가르는 1차 분기가 `status`/`successors`에서 나온다.
    DESIGN.md §3 ②의 설계 급소.
    """

    status: LawStatus
    current_name: str | None = None         # 개명/약칭 해소 시 현행 풀네임
    name_form: str = "exact"
    # 인용명이 현행명과 어떻게 연결됐나: exact|alias(공식약칭)|partial(부분명)|rename
    alive_articles: set = field(default_factory=set)
    # RENAMED일 때 현행본의 '살아있는 조(條) 키' 집합(예: {"제5조","제17조의2"}).
    # 인용 조문이 이 안에 있으면 깨끗한 개명(A), 없으면 전부개정·재번호(B) 신호.
    successors: list[str] = field(default_factory=list)
    # successors: 확정 후속법(수동/fixture가 채운 정비 후 값).
    #   0개 → D/E 후보, 1개 → B 후보, N개 → C 후보. classifier가 이걸로 자동 분류.

    # --- 폐지법 상세(부칙·제개정이유) 파싱 신호 — 자동 보강용 ---
    # 검색 API엔 없고 lawService.do 상세 산문에서 추출. 확정이 아니라 '후보/신호'.
    successor_candidates: list[str] = field(default_factory=list)
    # 산문에서 뽑은 후속법 후보(「」 인용). 제안에는 쓰되 category 자동확정엔 안 씀.
    absorbed: bool = False        # "일반회계로 흡수·통합" 등 → 후속법 없는 D 강신호
    repeal_reason: str = ""       # 제개정이유 발췌(리포트 note용)

    raw: dict = field(default_factory=dict)  # API 원응답 보존(디버깅/확장용)


@dataclass
class Result:
    """③ Classifier 출력 — 최종 판정 레코드. ④ Reporter 입력."""

    citation: Citation
    history: HistoryInfo
    category: Category | None
    confidence: Confidence
    successor_suggestion: str | None = None
    flag: bool = False    # 수동 확인 필요 여부 (C/D/E)
    note: str = ""
