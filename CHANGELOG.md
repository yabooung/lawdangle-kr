# Changelog

이 프로젝트의 주요 변경사항을 기록한다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/),
버전은 [유의적 버전](https://semver.org/lang/ko/)을 따른다.

## [0.2.0] - 2026-07-03

로컬 실행만으로 법령 검색·조문 조회를 제공하는 Phase 1. 기존 죽은 참조 탐지와 결합.

### Added
- `client.py` — 법제처 OPEN API 저수준 HTTP 클라이언트(`LawClient`).
  재시도(지수 백오프)·타임아웃·**HTML 에러페이지 감지**를 단일 경로로 제공.
- `search_law(resolver, query, *, current_only, limit)` — 법령명·키워드 검색.
  결과 없으면 빈 리스트, 약칭/부분명은 정식 현행명으로 자동 확장.
- `get_law_text(resolver, law, article=None)` — 현행 조문 조회(전문 또는 특정 조문).
  항·호 표기는 조 단위로 환원, 약칭 해소 지원.
- 결과 모델 `LawSearchResult`, `LawText` (`models.py`).
- CLI 플래그: `--search <검색어>`(+`--current`), `--text <법령명> [조문]`.
- 단위 테스트 `test_client.py`, `test_search.py` (네트워크 mock, 오프라인 실행).

### Changed
- `LawGoKrResolver` 의 HTTP/재시도 로직과 행 정규화 헬퍼(`_norm`/`_as_rows`/
  `_exact`/`_latest`/`_mst_of`)를 `client.py` 로 추출해 resolver·search 가 공유.
  `LawGoKrResolver(oc, ..., client=...)` 로 클라이언트 주입 가능(테스트/재사용).

### Removed
- 내부 설계문서(`DESIGN.md`)를 repo·배포 산출물에서 제외(로컬 보관 전환).

## [0.1.1] - 2026-06

### Fixed
- PyPI README 상대링크 404 수정.
- `--help` 한글 출력 깨짐 수정(UTF-8 재설정을 `parse_args` 앞으로).

## [0.1.0] - 2026-06

### Added
- 최초 PyPI 배포 — 한국 법령 죽은 참조(폐지·개명·이관·사문화) 탐지 및 A~E 5분류.
