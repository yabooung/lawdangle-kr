"""Mapper 단위 테스트 — 유사도/순위(네트워크 불필요)."""

from __future__ import annotations

from lawdangle.mapper import jaccard, rank_correspondence, tokenize
from lawdangle.resolver import extract_articles_detailed, hang_num


def test_tokenize_drops_short_and_stopwords():
    toks = tokenize("시ㆍ도지사는 산업위기대응특별지역으로 지정 경우 규정")
    assert "산업위기대응특별지역으로" in toks
    assert "경우" not in toks  # stopword
    assert "는" not in toks    # 1글자 제외


def test_jaccard_bounds():
    assert jaccard(set(), {"가나"}) == 0.0
    a = {"산업위기", "지정", "지역"}
    assert jaccard(a, a) == 1.0
    assert 0 < jaccard(a, {"산업위기", "다른말", "또하나"}) < 1


def test_rank_picks_most_similar():
    old = "시도지사는 산업위기대응특별지역으로 지정 신청"
    succ = {
        "제10조": "산업통상부장관은 산업위기대응특별지역 지정 신청을 받은 경우 심의",
        "제50조": "이 법 시행에 필요한 사항은 대통령령으로 정한다",
        "제3조": "국가는 재정을 지원하여야 한다",
    }
    ranked = rank_correspondence(old, succ, top_k=3)
    assert ranked[0].article == "제10조"  # 가장 유사
    assert ranked[0].score >= ranked[-1].score


class _FakeResolver:
    """find_current_laws만 흉내내는 오프라인 가짜 resolver(법제처처럼 부분일치)."""
    def __init__(self, mapping):
        self.mapping = mapping  # 개념어 -> 법령명 리스트
    def find_current_laws(self, q):
        out = []
        for concept, laws in self.mapping.items():
            if concept in q:           # 실 API의 부분일치 흉내(토큰에 조사 붙어도 매칭)
                out.extend(laws)
        return list(dict.fromkeys(out))


def test_discover_successors_prefers_specific_term():
    from lawdangle.mapper import discover_successors
    fake = _FakeResolver({
        "산업위기대응특별지역": ["지역 산업위기 대응 및 지역경제 회복을 위한 특별법"],
        "관할행정구역으로": ["법1", "법2", "법3", "법4", "법5", "법6", "법7"],  # 너무 흔함 → 버림
    })
    text = "시도지사는 관할행정구역으로 산업위기대응특별지역으로 지정"
    out = discover_successors(fake, text, exclude=())
    assert out[0] == "지역 산업위기 대응 및 지역경제 회복을 위한 특별법"
    assert "법1" not in out  # max_per_term 초과 → 제외


def test_discover_successors_excludes_self():
    from lawdangle.mapper import discover_successors
    fake = _FakeResolver({"산업위기대응특별지역": ["옛법령명", "지역 산업위기 특별법"]})
    out = discover_successors(fake, "산업위기대응특별지역 지정", exclude=("옛법령명",))
    assert "옛법령명" not in out


def test_hang_num_parsing():
    assert hang_num("②") == 2
    assert hang_num("⑭") == 14
    assert hang_num("2") == 2
    assert hang_num("") is None


def test_extract_articles_detailed_structure():
    detail = {"법령": {"조문": {"조문단위": [
        {
            "조문번호": "10", "조문제목": "지정",
            "조문내용": "제10조(지정)",
            "항": [
                {"항번호": "①", "항내용": "① 장관은 지정 신청을 받는다"},
                {"항번호": "②", "항내용": "② 위원회 심의를 거친다"},
            ],
        }
    ]}}}
    d = extract_articles_detailed(detail)
    assert "제10조" in d
    assert set(d["제10조"]["hangs"]) == {1, 2}
    assert "심의" in d["제10조"]["hangs"][2]


def test_rank_skips_deleted_articles():
    old = "산업위기대응특별지역 지정"
    succ = {"제10조": "제10조 삭제 <2020.1.1>", "제11조": "산업위기대응특별지역 지정 절차"}
    ranked = rank_correspondence(old, succ, top_k=3)
    arts = [c.article for c in ranked]
    assert "제10조" not in arts  # 삭제 조문 제외
    assert "제11조" in arts
