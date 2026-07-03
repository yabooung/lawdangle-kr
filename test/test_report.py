"""Reporter 단위 테스트 — CSV/JSON/요약 (그동안 무커버리지였던 모듈)."""

from __future__ import annotations

import json

from lawdangle import report
from lawdangle.models import (
    Category,
    Citation,
    Confidence,
    HistoryInfo,
    LawStatus,
    Result,
)


def _result(cat=Category.B, flag=True, note="이관"):
    return Result(
        citation=Citation("인용법", "제1조", "대상법", "제5조"),
        history=HistoryInfo(status=LawStatus.REPEALED),
        category=cat,
        confidence=Confidence.MEDIUM,
        successor_suggestion="새법",
        flag=flag,
        note=note,
    )


def test_csv_uses_lf_not_crlf():
    # \r\n 이면 파일 저장 시 Windows에서 \r\r\n 로 깨진다 → \n 이어야 함.
    out = report.to_csv([_result()])
    assert "\r" not in out
    assert out.startswith("citing_law,")


def test_csv_row_count():
    out = report.to_csv([_result(), _result(cat=Category.D)])
    rows = [l for l in out.splitlines() if l]
    assert len(rows) == 3  # 헤더 + 2건


def test_summarize_distribution_and_severity():
    results = [_result(Category.A), _result(Category.C), _result(Category.D),
               _result(Category.E)]
    s = report.summarize(results)
    assert s["total"] == 4 and s["classified"] == 4
    assert s["distribution"] == {"A": 1, "B": 0, "C": 1, "D": 1, "E": 1}
    assert s["high_severity_ECD"] == 3  # E+C+D


def test_summarize_counts_normal_and_unknown():
    normal = Result(
        citation=Citation("a", "b", "c", None),
        history=HistoryInfo(status=LawStatus.CURRENT),
        category=None, confidence=Confidence.HIGH,
    )
    s = report.summarize([normal, _result()])
    assert s["classified"] == 1 and s["normal_or_unknown"] == 1


def test_json_roundtrip():
    data = json.loads(report.to_json([_result()]))
    assert data["summary"]["total"] == 1
    assert data["results"][0]["category"] == "B"
    assert data["results"][0]["cited_article"] == "제5조"
