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
