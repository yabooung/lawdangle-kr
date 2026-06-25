"""`lawdangle <법령ID 또는 파일>` — 한 줄 실행.

DESIGN.md §3 ④ / §4.
파이프라인: parse → resolve → classify → report.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import report
from .classifier import classify
from .mapper import enrich_result, suggest_mapping
from .parser import parse_citations
from .resolver import FixtureResolver, LawGoKrResolver, Resolver
from .models import Result


def _build_resolver(args) -> Resolver:
    """--fixture 우선, 없으면 OC(법제처 API 키)로 라이브 resolver."""
    if args.fixture:
        return FixtureResolver.from_files(*args.fixture)
    oc = args.oc or os.environ.get("LAW_OC")
    if not oc:
        sys.exit(
            "법제처 API 키(OC)가 없습니다. --oc 또는 LAW_OC 환경변수, "
            "또는 오프라인이면 --fixture <연혁.json> 을 지정하세요."
        )
    return LawGoKrResolver(oc)


def run(
    text: str, resolver: Resolver, *, citing_law: str = "", deep: bool = False
) -> list[Result]:
    """파이프라인 한 번: 텍스트 → 판정 결과 리스트.

    deep=True 면 B/이관·개명+조문이동 건에 구체 대응 조문 제안까지 붙인다
    (라이브 resolver 필요 — 조문 매핑은 네트워크 조회).
    """
    citations = parse_citations(text, citing_law=citing_law)
    results = [classify(c, resolver.resolve(c.cited_law_name)) for c in citations]
    if deep and isinstance(resolver, LawGoKrResolver):
        results = [enrich_result(r, resolver) for r in results]
    return results


def run_law(law_name: str, resolver: LawGoKrResolver, *, deep: bool = False) -> list[Result]:
    """법령명으로 현행 본문을 직접 가져와 조 단위로 죽은 인용을 분석한다.

    텍스트 붙여넣기의 약점(판례 혼입·표기깨짐·citing_article 미상)을 피하는
    권장 입력 경로. 각 조문에서 인용을 추출하고 citing_article을 채운다.
    """
    arts = resolver.current_articles(law_name)
    if not arts:
        raise ValueError(f"현행 법령 「{law_name}」을(를) 찾지 못했습니다(법령명 확인).")
    results: list[Result] = []
    for art_key, body in arts.items():
        for c in parse_citations(body, citing_law=law_name, citing_article=art_key):
            r = classify(c, resolver.resolve(c.cited_law_name))
            if deep:
                r = enrich_result(r, resolver)
            results.append(r)
    return results


def _run_map(args) -> int:
    """--map 옛법령 조문 후속법령 → 조문 대응 순위 제안(라이브 전용)."""
    oc = args.oc or os.environ.get("LAW_OC")
    if not oc:
        sys.exit("조문 대응 제안은 법제처 API 키(--oc 또는 LAW_OC)가 필요합니다.")
    old_law, article, successor = args.map
    s = suggest_mapping(LawGoKrResolver(oc), old_law, article, successor)

    print(f"옛 법령 : 「{s.old_law}」 {s.old_article}"
          + (f"  (실본문 {s.old_article_version} 시행본)" if s.old_article_version else ""))
    if s.old_snippet:
        print(f"옛 조문 : {s.old_snippet}…")
    print(f"후속법령: 「{s.successor_law}」")
    print(f"판정    : {'유력' if s.confident else '수동확인'} — {s.note}")
    if s.candidates:
        print("후보(유사도순):")
        for i, c in enumerate(s.candidates, 1):
            print(f"  {i}. {c.article}  (유사도 {c.score})  {c.snippet}…")
    else:
        print("후보: 없음")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="lawdangle",
        description="현행 법령의 죽은 참조(폐지·개명·이관·사문화)를 탐지·5분류.",
    )
    p.add_argument(
        "input",
        nargs="?",
        help="법령 본문 텍스트 파일 경로 (- 는 표준입력). --law/--map 모드에선 생략",
    )
    p.add_argument(
        "--law",
        metavar="법령명",
        help="법령명으로 현행 본문을 가져와 조 단위로 분석(권장 입력, 라이브)",
    )
    p.add_argument(
        "--map",
        nargs=3,
        metavar=("옛법령", "조문", "후속법령"),
        help="조문 대응 제안: 옛(폐지) 법의 조문이 후속법 어느 조문에 대응하는지 순위 제시",
    )
    p.add_argument("--citing-law", default="", help="인용하는 쪽 법령명(리포트용)")
    p.add_argument("--oc", help="법제처 OPEN API 인증키(OC). 없으면 LAW_OC 환경변수")
    p.add_argument(
        "--fixture",
        nargs="+",
        help="오프라인 연혁 fixture JSON (지정 시 API 미사용)",
    )
    p.add_argument(
        "--format",
        choices=("csv", "json", "summary"),
        default="summary",
        help="출력 형식 (기본 summary)",
    )
    p.add_argument(
        "--deep",
        action="store_true",
        help="B/개명+조문이동 건에 구체 대응 조문까지 매핑(라이브, 느림)",
    )
    p.add_argument("-o", "--output", help="출력 파일 (미지정 시 표준출력)")
    args = p.parse_args(argv)

    # Windows 콘솔(cp949) 등에서 한글/em-dash 출력 깨짐·크래시 방지.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    # --- 조문 대응 제안 모드 -------------------------------------------- #
    if args.map:
        return _run_map(args)

    # --- 법령명 분석 모드(권장) ----------------------------------------- #
    if args.law:
        oc = args.oc or os.environ.get("LAW_OC")
        if not oc:
            sys.exit("--law 모드는 법제처 API 키(--oc 또는 LAW_OC)가 필요합니다.")
        try:
            results = run_law(args.law, LawGoKrResolver(oc), deep=args.deep)
        except ValueError as e:
            sys.exit(str(e))
    else:
        if not args.input:
            p.error("input 파일이 필요합니다 (또는 --law / --map 모드를 쓰세요)")
        if args.input == "-":
            text = sys.stdin.read()
        else:
            text = Path(args.input).read_text(encoding="utf-8")
        resolver = _build_resolver(args)
        results = run(text, resolver, citing_law=args.citing_law, deep=args.deep)

    if args.format == "csv":
        out = report.to_csv(results)
    elif args.format == "json":
        out = report.to_json(results)
    else:
        out = report.format_summary(results)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        # 요약은 콘솔에도 한 번 보여준다.
        print(report.format_summary(results), file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
