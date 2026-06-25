"""법제처 OPEN API raw 응답 프로브 — UTF-8 파일로 덤프.

DESIGN.md §5 2번 — resolver 필드 매핑/분기 신호 확정용.
현행/폐지/이관 법령이 어떤 target에서 어떤 필드로 떨어지는지 확인.

실행:  python examples/probe_api.py <OC> <출력디렉터리>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

BASE = "http://www.law.go.kr/DRF"

# (라벨, target, query) — 같은 법을 여러 target/표기로 때려본다.
PROBES = [
    ("hyeonhaeng_minbeob",        "law",   "민법"),
    ("repealed_gukyu",            "law",   "국유재산관리특별회계법"),
    ("repealed_gukyu_partial",    "law",   "국유재산"),
    ("repealed_gyunhyeong",       "law",   "국가균형발전 특별법"),
    ("repealed_gyunhyeong_ns",    "law",   "국가균형발전특별법"),
    # 연혁/시행일 target도 시도 — 폐지법이 여기서 잡히는지
    ("hist_gukyu_eflaw",          "eflaw", "국유재산관리특별회계법"),
    ("hist_gukyu_lsHstInf",       "lsHstInf", "국유재산관리특별회계법"),
]


def fetch(oc: str, target: str, query: str) -> dict:
    params = {"OC": oc, "target": target, "type": "JSON", "query": query}
    resp = requests.get(f"{BASE}/lawSearch.do", params=params, timeout=10)
    try:
        return {"_status": resp.status_code, **resp.json()}
    except json.JSONDecodeError:
        return {"_status": resp.status_code, "_raw_text": resp.text[:3000]}


def main() -> int:
    oc = sys.argv[1]
    outdir = Path(sys.argv[2] if len(sys.argv) > 2 else "probe_out")
    outdir.mkdir(parents=True, exist_ok=True)

    index = {}
    for label, target, query in PROBES:
        data = fetch(oc, target, query)
        f = outdir / f"{label}.json"
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # totalCnt만 콘솔에 (ASCII-safe)
        ls = data.get("LawSearch", {})
        index[label] = {
            "target": target,
            "totalCnt": ls.get("totalCnt", "?"),
            "resultMsg": ls.get("resultMsg", data.get("_raw_text", "")[:60]),
        }
    print(json.dumps(index, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
