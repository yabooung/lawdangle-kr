# -*- coding: utf-8 -*-
"""citation_graph_kit 검수 엑셀 → lawdangle 재분석/비교 어댑터.

자매 도구가 만든 '현행법_인용결함_검수_*.xlsx'의 행을 lawdangle Citation으로
변환해 라이브 재분류하고, 자매 도구 제안분류와 나란히 비교한다.

사용:  python examples/analyze_xlsx.py <xlsx경로> [시트인덱스=3] [건수=10]
"""

from __future__ import annotations

import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lawdangle.classifier import classify          # noqa: E402
from lawdangle.models import Citation               # noqa: E402
from lawdangle.resolver import LawGoKrResolver      # noqa: E402

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _read_rows(xlsx: str, sheet_idx: int) -> list[list[str]]:
    z = zipfile.ZipFile(xlsx)
    ss: list[str] = []
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{NS}si"):
            ss.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    except KeyError:
        pass

    def colnum(ref: str) -> int:
        c = re.match(r"[A-Z]+", ref).group()
        n = 0
        for ch in c:
            n = n * 26 + (ord(ch) - 64)
        return n

    root = ET.fromstring(z.read(f"xl/worksheets/sheet{sheet_idx}.xml"))
    rows = []
    for row in root.findall(f"{NS}sheetData/{NS}row"):
        cells: dict[int, str] = {}
        for c in row.findall(f"{NS}c"):
            t = c.get("t")
            v = c.find(f"{NS}v")
            if t == "inlineStr":
                isn = c.find(f"{NS}is")
                val = "".join(x.text or "" for x in isn.iter(f"{NS}t")) if isn is not None else ""
            elif v is None:
                val = ""
            else:
                val = v.text
                if t == "s":
                    val = ss[int(val)]
            cells[colnum(c.get("r"))] = val
        maxc = max(cells) if cells else 0
        rows.append([cells.get(i, "") for i in range(1, maxc + 1)])
    return rows


_ART_RE = re.compile(r"(제\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+호)?)")


def main() -> int:
    xlsx = sys.argv[1]
    sheet_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    oc_env = __import__("os").environ.get("LAW_OC")
    if not oc_env:
        env = Path(__file__).resolve().parents[1] / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.lower().startswith("oc="):
                    oc_env = line.split("=", 1)[1].strip()
    resolver = LawGoKrResolver(oc_env)

    rows = _read_rows(xlsx, sheet_idx)
    hdr = rows[0]
    # 컬럼 인덱스 찾기
    col = {name: hdr.index(name) for name in hdr}
    ci_citing = col.get("인용법령명(현행)")
    ci_citingart = col.get("인용조항")
    ci_cited = col.get("인용된 법령명(현행과 다름)")
    ci_quote = col.get("원문 인용구")
    ci_auto = col.get("자동분류(제안)")

    print(f"{'인용법령':<22}{'인용대상':<22}{'시트분류':<14}{'lawdangle':<8}일치?")
    print("-" * 80)
    agree = disagree = 0
    for r in rows[1 : 1 + n]:
        def g(i):
            return r[i] if i is not None and i < len(r) else ""
        cited = g(ci_cited)
        quote = g(ci_quote)
        m = _ART_RE.search(quote)
        cited_art = m.group(1) if m else None
        cit = Citation(g(ci_citing), g(ci_citingart), cited, cited_art)
        res = classify(cit, resolver.resolve(cited))
        ld = res.category.name if res.category else "-"
        sheet_cat = g(ci_auto)
        sheet_letter = sheet_cat[0] if sheet_cat else "?"
        same = "○" if ld == sheet_letter else "✗ ←주목"
        if ld == sheet_letter:
            agree += 1
        else:
            disagree += 1
        print(f"{g(ci_citing)[:20]:<22}{cited[:20]:<22}{sheet_cat[:12]:<14}{ld:<8}{same}")
    print("-" * 80)
    print(f"일치 {agree} / 불일치 {disagree}  (불일치 = lawdangle가 다르게 본 것)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
