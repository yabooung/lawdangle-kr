"""0.3.1 회귀 — 시행예정(PENDING) 판정 + 짧은 법명 페이징 + resolve_by_id.

전부 FakeClient(오프라인). 실측 근거는 CHANGELOG [0.3.1] 참조.
"""

from __future__ import annotations

from lawdangle.classifier import classify
from lawdangle.models import Citation, LawStatus
from lawdangle.resolver import LawGoKrResolver


def _row(name: str, code: str, law_id: str = "000001", *,
         gubun: str = "일부개정", enforce: str = "20250101", mst: str = "100") -> dict:
    return {
        "법령명한글": name,
        "현행연혁코드": code,
        "법령ID": law_id,
        "제개정구분명": gubun,
        "시행일자": enforce,
        "법령일련번호": mst,
    }


class FakeClient:
    """(target, query|ID, page) → 응답을 미리 박아둔 오프라인 클라이언트.

    search_map: {(target, query, page or 1): [rows]}
    id_map:     {(target, law_id): [rows]}
    """

    PAGE_SIZE = 100

    def __init__(self, search_map=None, id_map=None, total_map=None):
        self._search = search_map or {}
        self._ids = id_map or {}
        self._totals = total_map or {}

    @staticmethod
    def _wrap(rows, total=None):
        return {"LawSearch": {"law": rows, "totalCnt": total if total is not None else len(rows)}}

    def search(self, target, query, *, page=None):
        key = (target, query, page or 1)
        rows = self._search.get(key, [])
        return self._wrap(rows, self._totals.get((target, query)))

    def search_by_id(self, target, law_id):
        return self._wrap(self._ids.get((target, law_id), []))

    def service(self, target, mst):
        return {}

    def get(self, endpoint, extra, **kw):
        return {}  # 약칭사전(lsAbrv) 등 — 오프라인에선 빈 응답


def _resolver(**kw) -> LawGoKrResolver:
    return LawGoKrResolver(oc="test", enrich=False, client=FakeClient(**kw))


# --- PENDING: 시행예정 법령을 REPEALED 로 오판하지 않는다 ------------------- #

def test_pending_not_repealed():
    """제정 공포·시행일 미도래: 현행 검색 0건 + 연혁 전부 '시행예정' → PENDING."""
    r = _resolver(search_map={
        ("law", "새법", 1): [],
        ("eflaw", "새법", 1): [_row("새법", "시행예정", gubun="제정", enforce="20270318")],
    })
    info = r.resolve("새법")
    assert info.status == LawStatus.PENDING
    assert info.current_name == "새법"


def test_pending_classify_is_normal():
    """PENDING 은 죽은 참조가 아님 — category=None, 폐지 오알림 차단."""
    r = _resolver(search_map={
        ("law", "새법", 1): [],
        ("eflaw", "새법", 1): [_row("새법", "시행예정", gubun="제정")],
    })
    res = classify(
        Citation(citing_law="", citing_article="", cited_law_name="새법", cited_article=None),
        r.resolve("새법"),
    )
    assert res.category is None
    assert "시행예정" in res.note


def test_explicit_repeal_beats_pending():
    """제개정구분명에 '폐지' 명시면 시행예정 행이 있어도 REPEALED (폐지 우선)."""
    r = _resolver(search_map={
        ("law", "구법", 1): [],
        ("eflaw", "구법", 1): [
            _row("구법", "시행예정", gubun="타법폐지", enforce="20270101"),
            _row("구법", "연혁", enforce="20200101"),
        ],
    })
    assert r.resolve("구법").status == LawStatus.REPEALED


def test_history_only_still_repealed():
    """연혁만 남은 진짜 폐지는 그대로 REPEALED (기존 동작 회귀)."""
    r = _resolver(search_map={
        ("law", "구법", 1): [],
        ("eflaw", "구법", 1): [_row("구법", "연혁", gubun="폐지")],
    })
    assert r.resolve("구법").status == LawStatus.REPEALED


# --- 페이징: 짧은 법명 정확일치가 뒷페이지에 있어도 찾는다 ------------------ #

def test_exact_match_found_on_second_page():
    """'상법' 실측 케이스: 1페이지는 부분매칭 노이즈뿐 → 2페이지에서 정확일치."""
    noise = [_row(f"…보상법{i}", "현행", law_id=f"9{i:05d}") for i in range(100)]
    r = _resolver(
        search_map={
            ("law", "상법", 1): noise,
            ("law", "상법", 2): [_row("상법", "현행", law_id="001702")],
        },
        total_map={("law", "상법"): 101},
    )
    info = r.resolve("상법")
    assert info.status == LawStatus.CURRENT
    assert info.current_name == "상법"


def test_paging_stops_at_total():
    """totalCnt 이내에서 못 찾으면 페이지 낭비 없이 종료 → UNKNOWN."""
    r = _resolver(
        search_map={("law", "없는법", 1): [], ("eflaw", "없는법", 1): []},
        total_map={("law", "없는법"): 0, ("eflaw", "없는법"): 0},
    )
    assert r.resolve("없는법").status == LawStatus.UNKNOWN


# --- resolve_by_id: ID 직조회 ------------------------------------------------ #

def test_resolve_by_id_current():
    """현행 ID → 이름 검색 함정과 무관하게 CURRENT."""
    r = _resolver(id_map={("law", "001702"): [_row("상법", "현행", law_id="001702")]})
    info = r.resolve_by_id("001702", "상법")
    assert info.status == LawStatus.CURRENT
    assert info.current_name == "상법"


def test_resolve_by_id_renamed():
    """ID 는 현행에 살아있는데 이름이 다름 → RENAMED + 현행명."""
    r = _resolver(id_map={("law", "000100"): [_row("새이름법", "현행", law_id="000100")]})
    info = r.resolve_by_id("000100", "옛이름법")
    assert info.status == LawStatus.RENAMED
    assert info.current_name == "새이름법"


def test_resolve_by_id_pending_via_name_history():
    """현행에 ID 없음 → 이름 연혁으로 시행예정 판정 (eflaw 는 ID 검색 불가)."""
    r = _resolver(
        search_map={("eflaw", "새법", 1): [_row("새법", "시행예정", law_id="015068", gubun="제정")]},
        id_map={("law", "015068"): []},
    )
    info = r.resolve_by_id("015068", "새법")
    assert info.status == LawStatus.PENDING


def test_resolve_by_id_filters_same_id():
    """같은 이름의 다른 법령(재제정) 행이 섞여도 요청 ID 행으로 판정."""
    r = _resolver(
        search_map={("eflaw", "동명법", 1): [
            _row("동명법", "연혁", law_id="000200", gubun="폐지", enforce="20100101"),
            _row("동명법", "시행예정", law_id="000201", gubun="제정", enforce="20270101"),
        ]},
        id_map={("law", "000200"): []},
    )
    # 000200(폐지된 옛 법)을 물었으니 000201(신법)의 시행예정에 오염되면 안 됨.
    assert r.resolve_by_id("000200", "동명법").status == LawStatus.REPEALED


def test_resolve_by_id_unknown_without_name():
    """현행에 없고 이름도 없으면 연혁 판정 불가 → UNKNOWN."""
    r = _resolver(id_map={("law", "999999"): []})
    assert r.resolve_by_id("999999").status == LawStatus.UNKNOWN
