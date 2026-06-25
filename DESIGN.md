# lawdangle-kr — 설계 문서

> **lawdangle-kr** — Dead Cross-Reference Detector for Korean Statutes
> 현행 법령이 인용하는 대상 법령의 **폐지·개명·이관·사문화**를 탐지하고 5분류로 태깅한다.

---

## 네이밍

| 용도 | 이름 | 비고 |
|---|---|---|
| PyPI 배포명 / 레포명 | **`lawdangle-kr`** | 스코프(한국 법령 전용)를 정직하게 표기. 법제처 API·한국 입법체계(타법개정·전부개정·폐지제정)에 종속되므로 `-kr` 명시 |
| import 모듈명 | **`lawdangle`** | 코드 안에서는 짧게 — `from lawdangle import ...` |
| CLI 명령 | **`lawdangle`** | `lawdangle <법령ID 또는 파일>` |

- **어원:** law + *dangling reference* — 포인터/링크가 죽은 대상을 가리키는 기술 용어. 개발자에게 "법령판 dangling reference 검출기"로 즉시 전달됨.
- **`-kr`를 붙이는 이유:** 다른 나라 법령 도구로 오해/충돌 방지 + 향후 코어(`lawdangle`) + 국가별 어댑터(`-kr`) 확장 여지.
- **피한 형태:** `krlawdangle`(검색 불리), `lawdanglekr`(kr이 안 보임), `lawcheck`(너무 일반적, 아류로 보임).
- **확정 전 체크:** PyPI에 `lawdangle-kr` 비어 있는지 확인 후 선점.
- 참고: pip는 배포명의 하이픈/언더스코어를 동일 취급(`lawdangle-kr` ↔ `lawdangle_kr`)하지만 import는 불가 → **배포명 `lawdangle-kr` / import명 `lawdangle`** 분리가 깔끔.

---

## 0. 한 줄 정의 (README 최상단에 그대로 쓸 문장)

기존 인용 검증 도구는 "인용된 조문이 **실존하느냐**"까지만 본다.
이 도구는 "인용된 법령이 **아직 살아있는 좌표를 가리키느냐**"를 본다.
— 즉, 폐지·개명·이관·사문화된 죽은 참조(dangling reference)를 잡는다.

### 기존 도구와의 경계 (반박 차단용)

| | 검증하는 것 | 예시 |
|---|---|---|
| 실존 검증 (예: verify_citations) | 인용하는 **쪽** 조문이 진짜냐 | "형법 제9999조" → 없음 |
| **이 도구 (liveness)** | 인용당하는 **대상**이 폐지/개명/이관됐냐 | "「국가균형발전 특별법」 제17조제2항" → 폐지·삭제됨 |

방향이 반대다. 전자는 텍스트 안의 가짜를 잡고, 후자는 텍스트 안의 죽은 참조를 잡는다.

---

## 1. 문제 정의

현행 법령(시행령 포함)의 본문은 다른 법령을 `「법령명」 제○조제○항제○호` 형태로 인용한다.
그런데 인용 대상 법령이 이후 개명·폐지·이관되어도, 인용하는 쪽 본문은 자동으로 갱신되지 않는다(타법개정 누락).
그 결과 살아있는 법이 죽은/낡은 좌표를 가리키는 상태가 발생한다.

**핵심 함정:** 법명 단순 치환(string replace)으로 정규화하면, 분할 이관·조문번호 변경 케이스에서 **틀린 곳을 더 틀린 곳으로** 보내는 오정정이 발생한다.

---

## 2. 5분류 (도구의 심장)

판정 축 두 개:
- **축1 — 대상 존재:** 인용 대상 제도/조문이 현행 체계에 존재하는가
- **축2 — 좌표 일치:** 인용에 적힌 (법명 + 조문번호)가 현행과 일치하는가

| 코드 | 유형 | 대상 존재 | 좌표 일치 | 작동 | 정비 방법 | 심각성 |
|---|---|---|---|---|---|---|
| **A** | 단순 개명 | O | 법명 X / 조문 O | O (해석규칙) | 법명만 교체 | 5 (낮음) |
| **B** | 전부개정·이관 (조문 대응) | O | 법명 X / 조문 X | O (승계규칙) | 법명+조문 교체 | 4 |
| **C** | 분할 승계 | O (1:N) | 법명 X / 조문 X | O | 호 단위 수동 매핑 | 2 (높음) |
| **D** | 사문화 (전제 소멸) | X | — | 보통 자체조문으로 작동 | 인용부 삭제·재구성 | 3 |
| **E** | 순수 폐지 (빈 참조) | X | — | X 가능 | 입법 보완 | 1 (최상) |

### 심각성 순위 (제보/정비 우선순위)
`E > C > D > B > A`
판정 기준: "수범자가 본문만으로 권리·의무를 확정할 수 있는가" + "정정 난이도".
임팩트는 **E·C·D**에 있다. A·B는 양은 많아도 단순 행정 정비.

### 검증된 실증 케이스 (정답지 / 회귀 테스트 고정값)

| 입력 | 인용 | 정답 | 근거 |
|---|---|---|---|
| 공유수면법 §13①14 | 「국가균형발전 특별법」 §17② | **B** | 제도는 「지역 산업위기 대응 및 지역경제 회복을 위한 특별법」 §10로 이관. 조문번호 §17②→§10 변경. 단순 법명치환 시 오정정(지방분권균형발전법 §17은 무관 조항) |
| 등기특별회계법 §3 | 「국유재산관리특별회계법」 §6 | **D** | 특별회계 자체가 폐지(2007.1.1)되어 일반회계로 흡수. "그 규정에 불구하고" 특례의 전제가 소멸. 세입·세출은 자체 각 호로 작동 |

> 이 2건은 `test/fixtures/`에 박아넣고, 출력이 B/D로 안 나오면 회귀 실패로 처리한다.

---

## 3. 파이프라인 (4단계)

```
[법령 텍스트]
   │
   ▼  ① 인용 추출 (Parser)
[ {citing_law, citing_article, cited_law_name, cited_article}, ... ]
   │
   ▼  ② 연혁 조회 (History Resolver) — 법제처 API
[ + {cited_law_status, successor_info, ...} ]
   │
   ▼  ③ 분류 (Classifier) — 5분류 + 신뢰도
[ + {category: A~E, confidence, flag} ]
   │
   ▼  ④ 리포트 (Reporter)
[CSV / JSON]
```

### 단계별 책임

#### ① Parser — 인용 추출
- 입력: 법령 본문 문자열(또는 법령 ID로 본문 fetch).
- 추출 단위: `「(법령명)」\s*(제\d+조(의\d+)?(\s*제\d+항)?(\s*제\d+호)?)`
- 출력: 인용 레코드 리스트. 한 조문에 여러 인용 가능.
- 주의:
  - 「」 안에 법령명이 아닌 게 들어오는 경우(고시명, 별표명) 필터.
  - 조문번호 한글표기(제5조제2항) ↔ API 코드(000500...) 변환 필요. (korean-law-mcp의 변환 로직 참고 가능)
  - 약칭(화관법 등)은 풀네임 정규화 후 조회.

#### ② History Resolver — 연혁 조회
- 입력: `cited_law_name`.
- 법제처 OPEN API로 해당 법령의 **현재 상태**를 조회.
- 분기에 필요한 신호 (※ 실제 필드명은 API 응답 확인 후 채울 것):
  - `제정·개정구분` 또는 `법령상태` → 현행 / 폐지 / 타법폐지   `// TODO: 필드명`
  - 폐지인 경우: **후속·대체법 정보**가 응답/연혁에 있는가   `// TODO: 후속법 필드 유무 확인`
  - 개명인 경우: 옛 명칭 ↔ 현행 명칭 매핑   `// TODO`
- 캐시: 같은 법령 반복 조회 많음 → law명 기준 캐시(TTL 24h 권장).

> ⚠️ 설계 급소: A vs (B/C/D/E)를 가르는 1차 분기가 이 필드에서 나온다.
> 폐지법의 후속법 정보가 API로 **단일하게** 떨어지면 B 자동판정 가능,
> 후속법이 **없으면** D/E 후보, **여럿이면** C 후보. 이 떨어지는 형태를 먼저 확인할 것.

#### ③ Classifier — 5분류
- 입력: 인용 레코드 + 연혁 정보.
- 자동 판정 가능 범위 / 수동 플래그 경계를 **명확히** 둔다.

```
판정 의사결정 트리:

1. cited_law 현행 유지?
   ├─ YES → 인용 법명이 현행명과 동일? 
   │         ├─ YES → 정상 (분류 대상 아님)
   │         └─ NO  → 약칭/표기차이 확인 후, 실제 개명이면 A
   └─ NO (개명/폐지)
        │
        2. 개명(법인격 동일, 내용 연속)?
        │    └─ YES → A
        │
        3. 폐지 → 후속법 정보 분석
             ├─ 후속법 1개 + 인용 조문에 대응 조문 확정 가능 → B
             ├─ 후속법 여러 개(내용 분산) → C  [FLAG: 수동 — 호 단위 매핑 필요]
             ├─ 후속법 없음 + 인용 조항이 자체 완결(대상 없어도 결론 남) → D  [FLAG: 수동 확인]
             └─ 후속법 없음 + 인용 효과가 적용 불능 → E  [FLAG: 수동 — 최우선 검토]
```

- **자동/수동 경계 (정직하게 둘 것):**
  - 자동 확정: A (개명 확인), B (후속법 단일 + 조문 대응 명확)
  - **수동 플래그 필수: C, D, E** — 이 셋은 "대상 제도가 어디로 갔는지 / 자체 완결인지 / 효과가 죽었는지"를 사람이 봐야 정확. 자동으로 단정하면 오탐.
- 각 결과에 `confidence: high|medium|low|manual_required` 부여.
- C/D/E를 억지로 자동 확정하지 않는 것이 이 도구의 신뢰도 핵심. (원본 시트가 "대체법 있으면 직접 찾아 메모"로 비워둔 것과 같은 이유)

#### ④ Reporter — 출력
- CSV 컬럼(권장):
  `citing_law, citing_article, cited_law_name, cited_article, cited_status, category(A~E), confidence, successor_suggestion, flag, note`
- 집계 요약: 전체 N건 중 A/B/C/D/E 분포 + 심각성 상위(E,C,D) 건수.
- 이 집계표가 곧 어필/제보/정비제안의 핵심 산출물.

---

## 4. 모듈 구조 (Python 독립 레포 기준)

```
lawdangle-kr/
├── README.md                  # §0 한 줄 정의 + 실증 2케이스 + 1줄 실행법
├── pyproject.toml             # name="lawdangle-kr", pip install 가능하게
├── src/
│   └── lawdangle/
│       ├── __init__.py
│       ├── parser.py          # ① 인용 추출
│       ├── resolver.py        # ② 법제처 API 연혁 조회 + 캐시
│       ├── classifier.py      # ③ 5분류 (도구의 심장)
│       ├── report.py          # ④ CSV/JSON 출력
│       ├── models.py          # 데이터클래스: Citation, HistoryInfo, Result
│       └── cli.py             # `lawdangle <법령ID 또는 파일>` 한 줄 실행
├── test/
│   └── fixtures/
│       ├── gongyusumyeon.json  # 공유수면법 → 정답 B
│       └── deunggi.json        # 등기특별회계법 → 정답 D
└── examples/
    └── sample_corpus.txt
```

### 데이터 모델 (models.py 스케치)

```python
from dataclasses import dataclass
from enum import Enum

class Category(Enum):
    A = "rename"            # 단순 개명
    B = "transfer_mapped"   # 이관, 조문 대응
    C = "split_succession"  # 분할 승계
    D = "obsolete"          # 사문화
    E = "dangling"          # 순수 폐지(빈 참조)

class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual_required"

@dataclass
class Citation:
    citing_law: str
    citing_article: str
    cited_law_name: str
    cited_article: str | None

@dataclass
class HistoryInfo:
    status: str              # 현행 / 폐지 / 타법폐지 ... // TODO: API 매핑
    current_name: str | None # 개명 시 현행명
    successors: list[str]    # 후속·대체법 (0개=D/E후보, 1개=B후보, N개=C후보)
    # ... API 응답 보고 확장

@dataclass
class Result:
    citation: Citation
    history: HistoryInfo
    category: Category | None
    confidence: Confidence
    successor_suggestion: str | None
    note: str
```

---

## 5. 구현 순서 (권장)

1. **models.py** — 자료구조부터 고정. 나머지가 여기 맞춰 붙는다.
2. **resolver.py** — 폐지법(국유재산관리특별회계법) 1건으로 API 응답 받아 **필드 매핑 확정**. ← 여기가 막히면 전체가 막힘. 제일 먼저.
3. **classifier.py** — 의사결정 트리 구현. 단, C/D/E는 플래그만 달고 자동 단정 금지.
4. **parser.py** — 정규식 + 조문번호 변환.
5. **report.py + cli.py** — CSV 떨구고 한 줄 실행.
6. **test/fixtures** — 공유수면법(B)·등기특별회계법(D) 회귀 고정.

> 2번이 전체의 급소. resolver가 폐지/개명/후속법을 어떤 필드로 떨어뜨리는지 확정되면 나머지는 기계적.

---

## 6. 스코프 경계 (안 할 것 / 함정)

- **안 할 것:** 자동 정정(법명 치환) 기능을 기본값으로 넣지 말 것. 이 도구는 "탐지·분류"까지. 자동 치환은 C/B에서 오정정을 낳으므로, 정정은 "제안(suggestion)"으로만, 적용은 사람이.
- **함정 1:** 약칭/표기 차이(가운뎃점 ㆍ, 띄어쓰기)를 개명으로 오판 → 정규화 후 비교.
- **함정 2:** 후속법 단일이라고 무조건 B 아님 — 조문 대응이 깨지면(조문번호 변경) A로 처리하면 틀림. B로 가되 조문 교체 필요 플래그.
- **함정 3:** "폐지=흠결"로 단정 금지. D는 작동하고, B도 작동한다. 효력 마비는 E(+일부 D)만. 리포트에서 이 톤을 유지해야 반박당하지 않음.

---

## 7. 공개 전략 (요약)

- **공개:** 도구(코드) + 검증된 2케이스 + 5분류 기준.
- **비공개 유지:** 원본 6,479건 전체 분류표(자산). 도구가 있으면 재생성 가능하므로 원본을 통째로 풀 이유 없음. 공개하려면 검증 완료 후 "정제 데이터셋"으로 별도.
- **연결:** korean-law-mcp 레포에 이슈 — "실존 검증 너머 liveness(폐지/이관) 검증" 차별점 + 본 레포 링크.
