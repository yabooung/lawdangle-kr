# lawdangle-kr

> **Dead Cross-Reference Detector for Korean Statutes**
> Detects and classifies references in in-force Korean laws that point to **repealed, renamed, transferred, or obsolete** target laws.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/yabooung/lawdangle-kr/blob/master/LICENSE)

**한국어 README → [README.ko.md](https://github.com/yabooung/lawdangle-kr/blob/master/README.ko.md)**

---

Existing citation-checkers verify only whether *the citing article itself exists*.
lawdangle asks a different question: **does the cited law still point at a living coordinate?** — that is, it catches *dangling references* to laws that have been repealed, renamed, transferred, or hollowed out.

| | Checks | Example |
|---|---|---|
| Existence check | Whether the **citing** article is real | "Criminal Act art. 9999" → does not exist |
| **lawdangle (liveness)** | Whether the **cited target** was repealed / renamed / transferred | "「National Balanced Development Special Act」 art. 17(2)" → repealed & transferred |

The direction is reversed: the former catches fakes inside the text; the latter catches dead references inside the text.

> **The core trap:** naive string-replacement of law names produces *mis-corrections* in split-transfer and article-renumbering cases — sending a wrong reference somewhere *more* wrong. lawdangle therefore **detects and proposes**, but never auto-applies corrections.

## The five categories

| Code | Type | Works? | Remedy | Severity |
|---|---|---|---|---|
| **A** | Simple rename | Yes | Replace name only | 5 (low) |
| **B** | Full amendment / transfer (article mapped) | Yes | Replace name + article | 4 |
| **C** | Split succession (1 → N) | Yes | Manual item-level mapping | 2 (high) |
| **D** | Obsolete (premise dissolved) | Usually self-contained | Delete / restructure the citation | 3 |
| **E** | Pure repeal (empty reference) | May break | Legislative fix | 1 (highest) |

Severity ranking (remediation priority): **E > C > D > B > A**.
**C / D / E are never auto-asserted** — they are flagged for human review with evidence attached. This restraint is the heart of the tool's reliability.

### Automatic classification scope (live API)

| Verdict | How | Confidence |
|---|---|---|
| In-force / Repealed | `target=law` · `eflaw` lookup | Auto (high) |
| **A — Rename** | **Law-ID continuity** (old name absent, same ID alive under a new name) + **cited-article survival check** | Auto (high) |
| **A — Official abbreviation** | Official abbreviation dictionary (`lsAbrv`, ~2,600 entries) → full name | Auto (high) |
| **A — Truncated name** | Conservative `endswith` partial match → full name | Auto (medium) |
| B — Rename + article moved | Renamed, but the cited article is deleted/renumbered in the current text → suggests `--map` | Auto candidate (medium) |
| B — Transfer / C — Split | Repeal + successor candidates (addendum back-trace + amendment-reason) → article mapping is manual | Flag + candidates |
| D — Obsolete / E — Repeal | Repeal + absorption signal (general account) / no successor | Flag |
| Informal abbreviation (not in dictionary) | Exact match fails → UNKNOWN (mis-match avoided on purpose) | — |

## Install

```bash
pip install lawdangle-kr
```

Requires Python 3.10+. Live lookups need a free **법제처(MOLEG) OPEN API** key (OC), issued at <https://open.law.go.kr>.

## Quick start

```bash
# RECOMMENDED — analyze a whole statute by name (fetches the in-force body itself).
# No copy-paste, no case-law contamination, and the citing article is filled in.
LAW_OC=your_oc lawdangle --law "공유수면 관리 및 매립에 관한 법률" --format csv

# Analyze pasted statute text
LAW_OC=your_oc lawdangle path/to/law.txt --format summary

# Offline demo (history fixtures — no API key needed)
lawdangle examples/sample_corpus.txt \
    --fixture test/fixtures/gongyusumyeon.json test/fixtures/deunggi.json \
    --format csv

# --deep: also map the concrete corresponding article for B / rename+moved cases
LAW_OC=your_oc lawdangle path/to/law.txt --format csv --deep

# Article-correspondence helper (old article → successor article)
# Successor auto-discovered when omitted (works for split transfers too):
LAW_OC=your_oc lawdangle --map "국가균형발전 특별법" "제17조제2항"
# ...or specify the successor explicitly:
LAW_OC=your_oc lawdangle --map "국가균형발전 특별법" "제17조제2항" \
    "지역 산업위기 대응 및 지역경제 회복을 위한 특별법"
```

```python
from lawdangle import run_law
from lawdangle.resolver import LawGoKrResolver

resolver = LawGoKrResolver("your_oc")
for r in run_law("공유수면 관리 및 매립에 관한 법률", resolver):
    if r.category:                              # skip live/normal references
        print(r.citation.citing_article, r.citation.cited_law_name,
              r.citation.cited_article, "→", r.category.name, "|", r.note)

# Or work at the citation level directly:
from lawdangle import parse_citations, classify
for c in parse_citations(open("law.txt", encoding="utf-8").read()):
    res = classify(c, resolver.resolve(c.cited_law_name))
    print(res.category, res.note)
```

## Pipeline

```
[statute text]
   ① Parser     extract 「law」 + article citations
   ② Resolver   MOLEG API — current status, rename, successors (cached)
   ③ Classifier 5-way decision tree (+ confidence, manual flag)
   ④ Reporter   CSV / JSON / summary
```

## How successor detection works (live)

The search API has no "successor law" field, but the **repealed-law detail** (`lawService.do`) does. lawdangle back-traces successors via two routes:

- **Repeal-by-other-law back-trace** — when a law was repealed by another law's *addendum* (`타법폐지`), the addendum header `Addendum(<the repealing law>) … repeals 「self」` names the **repealing law = the successor**.
  *e.g.* 저탄소 녹색성장 기본법 → 「기후위기 대응을 위한 탄소중립ㆍ녹색성장 기본법」; 국토이용관리법 → 「국토의 계획 및 이용에 관한 법률」.
- **Amendment-reason prose** — extracts 「successor law」 names from the enactment/amendment reason (filtering out the addendum's "amendments to other laws", which are collateral, and keeping only law-shaped names).
- **Absorption signal** (`absorbed`) — phrases like "…merged into the general account" mean *no successor law* → a strong **D** signal.

Candidate count drives the class: **1 → B (transfer)**, **2+ → C (split)**, **0 + absorption → D**. All are flagged for manual confirmation.

### Content-based successor discovery (split transfers)

The back-traced candidate is the *law's general successor* — which often differs from the *specific provision's* successor (the split-transfer trap). For example, 국가균형발전 특별법's general successor is 「지방자치분권 및 지역균형발전에 관한 특별법」, but its art. 17(2) 산업위기대응특별지역 scheme actually moved to a **different** law: 「지역 산업위기 대응 및 지역경제 회복을 위한 특별법」.

lawdangle finds that automatically: it takes the **distinctive concept terms** from the old article's text (e.g. *산업위기대응특별지역*) and searches current **law names** for them — the law that *defines* the scheme surfaces (usually a single hit), and article mapping follows. So `--map` works even when you do **not** supply the successor, and `--deep` attaches the discovered successor + article to B/C results.

## Article correspondence (`--map`, `--deep`)

For transfers (B), `--map` narrows "old §17(2) → which successor article?". It walks the old law's history to find the **last substantive text before deletion** (a cited article may have been deleted *before* the law itself was repealed), then ranks the successor's current articles by **text similarity**. When the citation has a paragraph (②), it further narrows **down to the paragraph** inside the top article (item-level stays manual — that is category C).

```
$ lawdangle --map "국가균형발전 특별법" "제17조제2항" "지역 산업위기 대응 및 지역경제 회복을 위한 특별법"

옛 법령 : 「국가균형발전 특별법」 제17조  (substantive text from the 2022-01-13 version)
후속법령: 「지역 산업위기 대응 및 지역경제 회복을 위한 특별법」
판정    : manual — multiple close candidates (possible split) (paragraph: §1, sim 0.205)
후보(by similarity):
  1. 제10조제1항  (0.18)   ① the Minister … upon receiving a designation application …
  2. 제12조       (0.176)  …
  3. 제9조        (0.172)  …
```

It surfaces the design's known answer **§17(2) → art. 10** as the #1 candidate (제10조제1항), while *not* auto-confirming (arts. 9/10/12 are close — possible split) and leaving the final call to a human. That is precisely how the "mis-correction" trap is avoided.

## Validated cases (regression fixtures)

| Input | Citation | Answer |
|---|---|---|
| 공유수면법 §13①14 | 「국가균형발전 특별법」 §17② | **B** — institution transferred to 「지역 산업위기 대응 및 지역경제 회복을 위한 특별법」 |
| 등기특별회계법 §3 | 「국유재산관리특별회계법」 §6 | **D** — special account abolished & absorbed into the general account; the citing article still works on its own |

These two are pinned in `test/fixtures/`; if the output is not B / D, the regression fails.

## Scope (what it deliberately does *not* do)

- It **detects and classifies** only. Automatic name-substitution is not a default — corrections are emitted as *suggestions*; a human applies them. (Auto-substitution causes mis-corrections in B/C cases.)
- It does **not** equate "repealed" with "defective". D works, B works; only E (and some D) actually breaks enforceability. The report keeps this tone so its findings hold up.
- Informal abbreviations not in the official dictionary resolve to UNKNOWN rather than risk a wrong match.

## Development

```bash
pip install -e ".[dev]"
pytest                     # offline tests run anywhere; live API tests run only when an OC key is present
```

Live tests read the OC key from `LAW_OC` or a local `.env` (`oc=...`); without it they are skipped.

See [DESIGN.md](https://github.com/yabooung/lawdangle-kr/blob/master/DESIGN.md) for the full design rationale.

## License

MIT — see [LICENSE](https://github.com/yabooung/lawdangle-kr/blob/master/LICENSE).
