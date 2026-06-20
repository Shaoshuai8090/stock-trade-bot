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
