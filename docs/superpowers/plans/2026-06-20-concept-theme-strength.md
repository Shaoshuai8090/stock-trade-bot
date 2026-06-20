# Concept Theme Strength Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich real A-share candidates with AkShare/Eastmoney concept board strength so the existing after-close theme scoring path uses real hot-topic data.

**Architecture:** Add a focused concept theme helper under `trade_signal_tool/providers/` that converts AkShare concept board and constituent data into stock-code theme assignments. Wire `AkShareProvider` to run that helper after candidate enrichment, keeping failures best-effort and preserving current strategy behavior.

**Tech Stack:** Python standard library, dataclasses, `unittest`, AkShare-compatible provider methods, existing `StockCandidate` dataclass.

---

### File Structure

- Create: `trade_signal_tool/providers/concept_theme_provider.py`
  - Owns concept board ranking, constituent fetching, code normalization, and assignment merging.
- Modify: `trade_signal_tool/providers/akshare_provider.py`
  - Adds constructor flags, creates the concept helper, and applies assignments after candidate enrichment.
- Modify: `tests/test_akshare_provider.py`
  - Adds fake AkShare concept APIs and provider-level tests proving candidates get theme fields and failures are non-fatal.
- No strategy file changes are required because `AfterCloseStrategy._theme_score()` already consumes `theme_rank` and `has_hot_theme`.

### Task 1: Concept Theme Helper

**Files:**
- Create: `trade_signal_tool/providers/concept_theme_provider.py`
- Create: `tests/test_concept_theme_provider.py`

- [ ] **Step 1: Write failing tests for ranking and assignment merging**

Create `tests/test_concept_theme_provider.py`:

```python
import unittest

from trade_signal_tool.providers.concept_theme_provider import ConceptThemeProvider


class FakeFrame:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        self.assert_orient = orient
        return self.records


class ConceptThemeAkshare:
    def __init__(self):
        self.concept_symbols = []

    def stock_board_concept_name_em(self):
        return FakeFrame(
            [
                {"板块名称": "机器人", "涨跌幅": 3.8},
                {"板块名称": "人工智能", "涨跌幅": 5.2},
                {"板块名称": "低空经济", "涨跌幅": 1.4},
            ]
        )

    def stock_board_concept_cons_em(self, symbol):
        self.concept_symbols.append(symbol)
        records = {
            "人工智能": [
                {"代码": "300001", "名称": "示例科技"},
                {"代码": "000001", "名称": "平安银行"},
            ],
            "机器人": [
                {"代码": "300001", "名称": "示例科技"},
                {"代码": "300002", "名称": "好日线"},
            ],
            "低空经济": [
                {"代码": "300003", "名称": "低空样本"},
            ],
        }
        return FakeFrame(records[symbol])


class FailingConstituentAkshare(ConceptThemeAkshare):
    def stock_board_concept_cons_em(self, symbol):
        if symbol == "人工智能":
            raise RuntimeError("constituents disconnected")
        return super().stock_board_concept_cons_em(symbol)


class ConceptThemeProviderTest(unittest.TestCase):
    def test_assigns_strongest_concept_when_stock_belongs_to_multiple_hot_concepts(self):
        ak = ConceptThemeAkshare()
        provider = ConceptThemeProvider(ak, hot_concept_limit=2)

        assignments = provider.assignments_for_codes(["300001", "000001", "300002"])

        self.assertEqual(assignments["300001"].theme, "人工智能")
        self.assertEqual(assignments["300001"].theme_rank, 1)
        self.assertEqual(assignments["000001"].theme, "人工智能")
        self.assertEqual(assignments["000001"].theme_rank, 1)
        self.assertEqual(assignments["300002"].theme, "机器人")
        self.assertEqual(assignments["300002"].theme_rank, 2)
        self.assertEqual(ak.concept_symbols, ["人工智能", "机器人"])

    def test_skips_failed_constituent_request_and_keeps_next_hot_concept(self):
        provider = ConceptThemeProvider(FailingConstituentAkshare(), hot_concept_limit=2)

        assignments = provider.assignments_for_codes(["300001", "300002"])

        self.assertEqual(assignments["300001"].theme, "机器人")
        self.assertEqual(assignments["300001"].theme_rank, 2)
        self.assertEqual(assignments["300002"].theme, "机器人")
        self.assertEqual(assignments["300002"].theme_rank, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_concept_theme_provider -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` because `trade_signal_tool.providers.concept_theme_provider` does not exist yet.

- [ ] **Step 3: Implement the helper**

Create `trade_signal_tool/providers/concept_theme_provider.py`:

```python
from dataclasses import dataclass
import math
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ThemeAssignment:
    theme: str
    theme_rank: int


class ConceptThemeProvider:
    def __init__(self, ak_module: Any, hot_concept_limit: int = 20):
        self.ak = ak_module
        self.hot_concept_limit = hot_concept_limit

    def assignments_for_codes(self, codes: Iterable[str]) -> Dict[str, ThemeAssignment]:
        wanted_codes = {_clean_code(code) for code in codes}
        if not wanted_codes or self.hot_concept_limit <= 0:
            return {}

        assignments: Dict[str, ThemeAssignment] = {}
        for rank, concept_name in self._hot_concepts():
            try:
                constituents = _records(self.ak.stock_board_concept_cons_em(symbol=concept_name))
            except Exception:
                continue
            for row in constituents:
                code = _clean_code(_first_present(row, ("代码", "股票代码", "code")))
                if code not in wanted_codes:
                    continue
                current = assignments.get(code)
                if current is None or rank < current.theme_rank:
                    assignments[code] = ThemeAssignment(theme=concept_name, theme_rank=rank)
        return assignments

    def _hot_concepts(self) -> List[tuple]:
        records = _records(self.ak.stock_board_concept_name_em())
        concepts = []
        for index, row in enumerate(records):
            name = str(_first_present(row, ("板块名称", "概念名称", "名称", "name")) or "").strip()
            if not name:
                continue
            concepts.append((index, name, _optional_float(_first_present(row, ("涨跌幅", "涨跌幅%", "change_pct")))))

        if any(change is not None for _, _, change in concepts):
            concepts.sort(key=lambda item: item[2] if item[2] is not None else -999.0, reverse=True)

        return [(rank, name) for rank, (_, name, _) in enumerate(concepts[: self.hot_concept_limit], start=1)]


def _records(frame: Any) -> List[Dict[str, Any]]:
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict("records"))
    return list(frame)


def _first_present(row: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip().replace("%", "")
    if not text or text in {"-", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_code(value: Any) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-6:].zfill(6) if digits else ""
```

- [ ] **Step 4: Run focused helper tests**

Run:

```bash
python3 -m unittest tests.test_concept_theme_provider -v
```

Expected: PASS for both helper tests.

- [ ] **Step 5: Commit helper and helper tests**

Run:

```bash
git add trade_signal_tool/providers/concept_theme_provider.py tests/test_concept_theme_provider.py
git commit -m "feat: add concept theme provider"
```

Expected: commit succeeds after helper tests pass.

### Task 2: Wire Concept Themes Into AkShareProvider

**Files:**
- Modify: `trade_signal_tool/providers/akshare_provider.py`
- Test: `tests/test_akshare_provider.py`

- [ ] **Step 1: Add failing tests for failure fallback and opt-out**

Add these fake classes near the other fake AkShare classes in `tests/test_akshare_provider.py`:

```python
class ConceptThemeAkshare(FakeAkshare):
    def __init__(self):
        super().__init__()
        self.concept_symbols = []

    def stock_board_concept_name_em(self):
        return FakeFrame(
            [
                {"板块名称": "机器人", "涨跌幅": 3.8},
                {"板块名称": "人工智能", "涨跌幅": 5.2},
                {"板块名称": "低空经济", "涨跌幅": 1.4},
            ]
        )

    def stock_board_concept_cons_em(self, symbol):
        self.concept_symbols.append(symbol)
        records = {
            "人工智能": [
                {"代码": "300001", "名称": "示例科技"},
                {"代码": "000001", "名称": "平安银行"},
            ],
            "机器人": [
                {"代码": "300001", "名称": "示例科技"},
                {"代码": "300002", "名称": "好日线"},
            ],
            "低空经济": [
                {"代码": "300003", "名称": "低空样本"},
            ],
        }
        return FakeFrame(records[symbol])


class FailingConceptNameAkshare(FakeAkshare):
    def stock_board_concept_name_em(self):
        raise RuntimeError("concept list disconnected")


class PartiallyFailingConceptConsAkshare(ConceptThemeAkshare):
    def stock_board_concept_cons_em(self, symbol):
        if symbol == "人工智能":
            raise RuntimeError("constituents disconnected")
        return super().stock_board_concept_cons_em(symbol)
```

Add these tests to `AkShareProviderTest`:

```python
def test_provider_enriches_candidates_with_strongest_concept_theme(self):
    ak = ConceptThemeAkshare()
    provider = AkShareProvider(
        ak_module=ak,
        today=date(2026, 6, 3),
        hot_concept_limit=2,
    )

    candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=2)

    by_code = {candidate.code: candidate for candidate in candidates}
    self.assertEqual(by_code["300001"].theme, "人工智能")
    self.assertEqual(by_code["300001"].theme_rank, 1)
    self.assertTrue(by_code["300001"].has_hot_theme)
    self.assertEqual(by_code["000001"].theme, "人工智能")
    self.assertEqual(by_code["000001"].theme_rank, 1)
    self.assertEqual(ak.concept_symbols, ["人工智能", "机器人"])


def test_provider_keeps_candidates_when_concept_list_fails(self):
    provider = AkShareProvider(
        ak_module=FailingConceptNameAkshare(),
        today=date(2026, 6, 3),
    )

    candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

    self.assertEqual(candidates[0].code, "300001")
    self.assertEqual(candidates[0].theme, "")
    self.assertIsNone(candidates[0].theme_rank)
    self.assertFalse(candidates[0].has_hot_theme)


def test_provider_skips_one_failed_concept_and_uses_next_hot_concept(self):
    provider = AkShareProvider(
        ak_module=PartiallyFailingConceptConsAkshare(),
        today=date(2026, 6, 3),
        hot_concept_limit=2,
    )

    candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

    self.assertEqual(candidates[0].code, "300001")
    self.assertEqual(candidates[0].theme, "机器人")
    self.assertEqual(candidates[0].theme_rank, 2)
    self.assertTrue(candidates[0].has_hot_theme)


def test_provider_can_disable_concept_theme_enrichment(self):
    ak = ConceptThemeAkshare()
    provider = AkShareProvider(
        ak_module=ak,
        today=date(2026, 6, 3),
        enable_concept_theme=False,
    )

    candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

    self.assertEqual(candidates[0].theme, "")
    self.assertIsNone(candidates[0].theme_rank)
    self.assertFalse(candidates[0].has_hot_theme)
    self.assertEqual(ak.concept_symbols, [])
```

- [ ] **Step 2: Run the focused provider tests to verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_akshare_provider.AkShareProviderTest.test_provider_enriches_candidates_with_strongest_concept_theme \
  tests.test_akshare_provider.AkShareProviderTest.test_provider_keeps_candidates_when_concept_list_fails \
  tests.test_akshare_provider.AkShareProviderTest.test_provider_skips_one_failed_concept_and_uses_next_hot_concept \
  tests.test_akshare_provider.AkShareProviderTest.test_provider_can_disable_concept_theme_enrichment \
  -v
```

Expected: FAIL until `AkShareProvider` accepts the new constructor options and applies concept assignments.

- [ ] **Step 3: Implement provider wiring**

Modify the imports at the top of `trade_signal_tool/providers/akshare_provider.py`:

```python
import importlib
import json
import math
from dataclasses import replace
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, Callable, Dict, Iterable, List, Optional

from trade_signal_tool.models import StockCandidate
from trade_signal_tool.providers.concept_theme_provider import ConceptThemeProvider
```

Modify `AkShareProvider.__init__` signature and body:

```python
    def __init__(
        self,
        ak_module: Optional[Any] = None,
        today: Optional[date] = None,
        import_module: Callable[[str], Any] = importlib.import_module,
        requests_get: Optional[Callable[..., Any]] = None,
        prefer_low_risk_spot: bool = False,
        enable_concept_theme: bool = True,
        hot_concept_limit: int = 20,
    ):
        if ak_module is None:
            try:
                ak_module = import_module("akshare")
            except ModuleNotFoundError as exc:
                raise RuntimeError("AkShare is required for real market data. Install it with: pip install akshare") from exc
        self.ak = ak_module
        self.today = today or date.today()
        self.requests_get = requests_get
        self.prefer_low_risk_spot = prefer_low_risk_spot
        self.enable_concept_theme = enable_concept_theme
        self.concept_theme_provider = ConceptThemeProvider(ak_module, hot_concept_limit=hot_concept_limit)
```

Modify the end of `fetch_candidates`:

```python
    def fetch_candidates(self, max_candidates: int = 80, enrich_limit: int = 20) -> List[StockCandidate]:
        spot_records = self._spot_records()
        rough = [record for record in spot_records if self._passes_rough_filters(record)]
        rough.sort(key=self._rough_rank_key, reverse=True)
        candidates = []
        for record in rough[: max_candidates]:
            candidate = self._enrich_record(record)
            if candidate is not None and self._passes_enriched_rough_filters(candidate):
                candidates.append(candidate)
            if len(candidates) >= enrich_limit:
                break
        return self._with_concept_themes(candidates)
```

Add this method to `AkShareProvider` after `fetch_candidates`:

```python
    def _with_concept_themes(self, candidates: List[StockCandidate]) -> List[StockCandidate]:
        if not self.enable_concept_theme or not candidates:
            return candidates
        try:
            assignments = self.concept_theme_provider.assignments_for_codes(candidate.code for candidate in candidates)
        except Exception:
            return candidates
        if not assignments:
            return candidates
        return [
            replace(
                candidate,
                theme=assignments[candidate.code].theme,
                theme_rank=assignments[candidate.code].theme_rank,
                has_hot_theme=True,
            )
            if candidate.code in assignments
            else candidate
            for candidate in candidates
        ]
```

- [ ] **Step 4: Run focused provider tests to verify they pass**

Run:

```bash
python3 -m unittest \
  tests.test_akshare_provider.AkShareProviderTest.test_provider_enriches_candidates_with_strongest_concept_theme \
  tests.test_akshare_provider.AkShareProviderTest.test_provider_keeps_candidates_when_concept_list_fails \
  tests.test_akshare_provider.AkShareProviderTest.test_provider_skips_one_failed_concept_and_uses_next_hot_concept \
  tests.test_akshare_provider.AkShareProviderTest.test_provider_can_disable_concept_theme_enrichment \
  -v
```

Expected: PASS for all four tests.

- [ ] **Step 5: Run full AkShare provider tests**

Run:

```bash
python3 -m unittest tests.test_akshare_provider -v
```

Expected: PASS. Existing tests use fake AkShare objects without concept methods; best-effort failure handling must keep them passing.

- [ ] **Step 6: Commit provider wiring**

Run:

```bash
git add trade_signal_tool/providers/akshare_provider.py tests/test_akshare_provider.py
git commit -m "feat: enrich candidates with concept themes"
```

Expected: commit succeeds.

### Task 3: Verification And Documentation Check

**Files:**
- Modify: `README.md`
- Test: full test suite

- [ ] **Step 1: Update README provider data-source notes**

Modify the README data-source section by adding concept boards to the bullet list:

```markdown
- AkShare/东方财富概念板块: 拉取热门概念板块和成分股，为候选股填充 `theme`、`theme_rank`、`has_hot_theme`
```

Modify the scoring section so the topic strength line says real providers now fill it:

```markdown
- 题材强度：25，真实行情通过 AkShare/东方财富概念板块填充热门题材排名；接口不可用时按中性题材评分
```

- [ ] **Step 2: Run full test suite**

Run:

```bash
python3 -m unittest discover -v
```

Expected: PASS for all tests.

- [ ] **Step 3: Run demo CLI smoke test**

Run:

```bash
python3 -m trade_signal_tool.cli scan --demo --json
```

Expected: exit code 0 and JSON containing a top-level `"signals"` key.

- [ ] **Step 4: Commit README and verification-ready state**

Run:

```bash
git add README.md
git commit -m "docs: document concept theme enrichment"
```

Expected: commit succeeds. If README already changed in an earlier task, this commit can include no changes and should be skipped after confirming `git status --short` is clean.

- [ ] **Step 5: Final status check**

Run:

```bash
git status --short
```

Expected: no output.

### Self-Review

- Spec coverage: The plan covers AkShare/Eastmoney concept board ranking, top-N limiting, constituent mapping, multi-concept strongest-rank selection, provider wiring for `akshare` and inherited `astock`, best-effort failures, opt-out configuration, and README documentation.
- Red-flag scan: No open planning gaps are present.
- Type consistency: `ThemeAssignment.theme`, `ThemeAssignment.theme_rank`, `ConceptThemeProvider.assignments_for_codes()`, `AkShareProvider.enable_concept_theme`, and `hot_concept_limit` are used consistently across tests and implementation steps.
