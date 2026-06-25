"""Resolver 단위 테스트 — 폐지법 상세 산문 파싱(네트워크 불필요)."""

from __future__ import annotations

from lawdangle.resolver import parse_repeal_detail

# 국유재산관리특별회계법 폐지법률 상세(발췌) — 일반회계 흡수 = 후속'법' 없음.
ABSORBED_DETAIL = {
    "법령": {
        "제개정이유": {
            "제개정이유내용": [[
                "[폐지]",
                "◇폐지이유 및 주요내용",
                "  국유재산관리특별회계를 폐지하고 그 재산 등을 일반회계로 통합운영하려는 것임.",
            ]]
        }
    }
}

# 후속법이 산문에 등장하는 케이스 — 「○○법」으로 이관.
TRANSFER_DETAIL = {
    "법령": {
        "제개정이유": {
            "제개정이유내용": [[
                "[폐지]",
                "  이 제도를 「지역 산업위기 대응 및 지역경제 회복을 위한 특별법」으로 이관함.",
            ]]
        }
    }
}


def test_absorbed_no_candidate():
    cand, absorbed, reason = parse_repeal_detail(ABSORBED_DETAIL, "국유재산관리특별회계법")
    assert absorbed is True
    assert cand == []
    assert "일반회계로 통합운영" in reason


def test_transfer_candidate_extracted():
    cand, absorbed, reason = parse_repeal_detail(TRANSFER_DETAIL, "구법")
    assert cand == ["지역 산업위기 대응 및 지역경제 회복을 위한 특별법"]
    assert absorbed is False  # 후보가 있으면 흡수로 보지 않음


def test_self_name_excluded():
    detail = {"법령": {"제개정이유": {"제개정이유내용": [["「구법」을 폐지한다"]]}}}
    cand, _, _ = parse_repeal_detail(detail, "구법")
    assert cand == []  # 자기 자신은 후보에서 제외
