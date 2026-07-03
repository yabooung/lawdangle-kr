# Changelog

이 프로젝트의 주요 변경사항을 기록한다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/),
버전은 [유의적 버전](https://semver.org/lang/ko/)을 따른다.

## [0.3.0] - 2026-07-03

죽은 참조 탐지(고유 강점)의 신뢰도 보강 — 실데이터 기반 회귀 대폭 확충.

### Added
- 등급별 실제 판정례 회귀 fixture 추가(라이브 API로 확인한 실제 법령 전이):
  - **A** 개명 — 기부금품법 → 기부문화 활성화법 (`gibu.json`)
  - **B** 이관 — 저탄소녹색성장기본법 → 탄소중립기본법 (`jeotanso.json`)
  - **C** 분할 — 음비게법 → 영화비디오물+게임산업 (`eumbin.json`)
  - **D** 폐지·무신호 — 사회보호법 (`sahoeboho.json`)
  - (기존 B 공유수면법, D 등기특별회계법 유지) → A/B/C/D 커버
- `test_live_api.py`: 등급별 실데이터 10건의 resolve 신호 회귀(약칭·부분명·개명·이관·분할·흡수·무신호·정상·UNKNOWN).

### Fixed (검색/조문 API 자체 감사)
- `normalize_article_key`: '제3장'·'제5호'·'제2항' 등 조가 아닌 단위를 조로 **오독**하던
  문제 수정 — 이제 거부(ValueError). '제5조', '제5조의2', '5'는 그대로 허용.
- `LawSearchResult.law_type`: 잘못된 필드명(`법종구분명`) 참조로 **항상 빈값**이던 것 →
  `법령구분명`으로 수정, 이제 채워짐.
- `LawText.law_id`·`enforce_date`: 미채움(항상 None) → 현행 법령 행에서 채움.
- `search_law`: 관련도 정렬 추가 — 법제처 부분일치로 '민법'→'난민법'이 섞여도
  정확·접두 일치를 앞에 둔다('민법'이 최상단).

### Fixed (전 모듈 병렬 감사 — 탐지 파이프라인)
- **classifier** — 표기만 다른 중복 후속법이 개수를 부풀려 단일 이관(B)을 분할 승계(C)로
  오분류하던 문제 수정(`successors`/`successor_candidates` 정규화 중복 제거).
- **classifier** — 개명(RENAMED)인데 인용 조문의 현행본 생존을 **확인 못한 경우**를
  '확인됨'과 똑같이 A/HIGH로 단정하던 과신 수정 → A로 보되 MEDIUM + 수동 플래그.
- **classifier** — 개명인데 `current_name`이 없으면 note에 리터럴 'None'이 찍히던 것 수정.
- **parser** — 「위원회」(정의어)·「제3호」(호 참조) 같은 비(非)법령 괄호를 법령으로
  오추출하던 문제 수정 — 법령 접미사(법/법률/령/규칙/규정/조례/조약/협정)로 끝나야 인정.
- **resolver** — `is_deleted`가 부분삭제 조('① 삭제 <날짜> ② 살아있는 내용')를 조 전체
  삭제로 오판하던 문제 수정 → 조 '전체'가 삭제된 형태만 True. (개명 A/B 판정 정확도 향상)
- **resolver** — `extract_articles`류가 API의 명시적 `null`(조문/항)에서 크래시하던 것 방어.
- **mapper** — `find_old_article_detailed`가 `_mst_of` 폴백을 안 써 MST가 상세링크에만 있는
  연혁행을 스킵(거짓 '본문 없음')하던 불일치 수정.
- **mapper** — 유사도 0에 가까운 후보를 `enrich_result`가 구체 대응 조문으로 단정하던 것
  수정 → `_CONFIDENT_MIN` 미만이면 '조문대응 불명(수동)'으로만 표기(설계 원칙 준수).

### Known limitations (감사에서 확인, 이번 릴리즈 미수정 — 오류 아님/트레이드오프)
- parser: 「」 법령명 '내부'의 개행은 통째 드랍(무한 매칭 방지 안전장치), 한 참조 안의
  조문 나열('제5조 및 제6조')은 첫 조만, 원문자 항(①②)은 미파싱 — 설계 범위.
- mapper: 유사도 토큰화가 순수 숫자·조사(을/를/이/가)를 구분하지 않음 — 순위 품질 한계이나
  매핑 결과는 애초에 '수동 확인용 제안'이라 오단정으로 이어지지 않음.

### Notes
- **E(효과 마비)는 classify가 자동 단정하지 않는다** — 후속법 없으면 보수적으로 D 기본 +
  수동 플래그. E 여부는 사람이 판단(오탐 차단, 도구 신뢰도의 핵심). 회귀는 A/B/C/D 검증.

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
