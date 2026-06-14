import csv
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

from trade_signal_tool.models import StockCandidate


def load_candidates_csv(path: Path) -> List[StockCandidate]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [candidate_from_row(row) for row in csv.DictReader(handle)]


def candidate_from_row(row: Mapping[str, str]) -> StockCandidate:
    return StockCandidate(
        code=row["code"],
        name=row["name"],
        board=row.get("board", ""),
        price=_float(row, "price"),
        pct_change=_float(row, "pct_change"),
        index_pct_change=_float(row, "index_pct_change"),
        current_volume=_int(row, "current_volume"),
        same_time_volumes_5d=_int_list(row.get("same_time_volumes_5d", "")),
        turnover_rate=_float(row, "turnover_rate"),
        float_market_cap_billion=_float(row, "float_market_cap_billion"),
        recent_daily_volumes=_int_list(row.get("recent_daily_volumes", "")),
        projected_daily_volume=_int(row, "projected_daily_volume"),
        ma5=_float(row, "ma5"),
        ma10=_float(row, "ma10"),
        ma20=_float(row, "ma20"),
        ma60=_float(row, "ma60"),
        ma60_prev=_float(row, "ma60_prev"),
        intraday_above_avg_ratio=_float(row, "intraday_above_avg_ratio"),
        recovered_after_avg_break=_bool(row.get("recovered_after_avg_break", "")),
        theme=row.get("theme", ""),
        theme_rank=_optional_int(row.get("theme_rank", "")),
        has_hot_theme=_bool(row.get("has_hot_theme", "")),
        pressure_distance_pct=_optional_float(row.get("pressure_distance_pct", "")),
        upper_shadow_recent=_bool(row.get("upper_shadow_recent", "")),
        is_st=_bool(row.get("is_st", "")),
        is_suspended=_bool(row.get("is_suspended", "")),
        listing_days=_int(row, "listing_days"),
        limit_up_seal_strength=_optional_float(row.get("limit_up_seal_strength", "")),
    )


def signals_to_dicts(signals: Iterable) -> List[dict]:
    return [signal.to_dict() for signal in signals]


def _int_list(value: str) -> List[int]:
    return [int(float(item.strip())) for item in value.split("|") if item.strip()]


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def _optional_int(value: str) -> Optional[int]:
    value = str(value).strip()
    return int(value) if value else None


def _optional_float(value: str) -> Optional[float]:
    value = str(value).strip()
    return float(value) if value else None


def _int(row: Mapping[str, str], key: str) -> int:
    return int(float(row[key]))


def _float(row: Mapping[str, str], key: str) -> float:
    return float(row[key])
