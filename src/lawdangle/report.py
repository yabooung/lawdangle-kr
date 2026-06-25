"""④ Reporter — CSV / JSON 출력 + 집계 요약.

DESIGN.md §3 ④.
집계표(A~E 분포 + 심각성 상위 E,C,D)가 곧 어필/제보/정비제안의 핵심 산출물.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter

from .models import Result

CSV_COLUMNS = [
    "citing_law",
    "citing_article",
    "cited_law_name",
    "cited_article",
    "cited_status",
    "category",
    "confidence",
    "successor_suggestion",
    "flag",
    "note",
]


def _row(r: Result) -> dict:
    return {
        "citing_law": r.citation.citing_law,
        "citing_article": r.citation.citing_article,
        "cited_law_name": r.citation.cited_law_name,
        "cited_article": r.citation.cited_article or "",
        "cited_status": r.history.status.value,
        "category": r.category.name if r.category else "",
        "confidence": r.confidence.value,
        "successor_suggestion": r.successor_suggestion or "",
        "flag": "1" if r.flag else "",
        "note": r.note,
    }


def to_csv(results: list[Result]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for r in results:
        writer.writerow(_row(r))
    return buf.getvalue()


def to_json(results: list[Result]) -> str:
    return json.dumps(
        {"results": [_row(r) for r in results], "summary": summarize(results)},
        ensure_ascii=False,
        indent=2,
    )


def summarize(results: list[Result]) -> dict:
    """전체 N건 중 A/B/C/D/E 분포 + 심각성 상위(E,C,D) 건수."""
    dist = Counter(r.category.name for r in results if r.category)
    classified = sum(dist.values())
    high_severity = dist["E"] + dist["C"] + dist["D"]
    return {
        "total": len(results),
        "classified": classified,
        "normal_or_unknown": len(results) - classified,
        "distribution": {k: dist.get(k, 0) for k in ("A", "B", "C", "D", "E")},
        "high_severity_ECD": high_severity,
        "flagged_manual": sum(1 for r in results if r.flag),
    }


def format_summary(results: list[Result]) -> str:
    """터미널 출력용 한 화면 요약."""
    s = summarize(results)
    d = s["distribution"]
    lines = [
        f"총 {s['total']}건 (분류 {s['classified']} / 정상·미확인 {s['normal_or_unknown']})",
        f"  A 개명 {d['A']}  B 이관 {d['B']}  C 분할 {d['C']}  D 사문화 {d['D']}  E 폐지 {d['E']}",
        f"  ▲ 심각성 상위(E·C·D): {s['high_severity_ECD']}건   수동확인 플래그: {s['flagged_manual']}건",
    ]
    return "\n".join(lines)
