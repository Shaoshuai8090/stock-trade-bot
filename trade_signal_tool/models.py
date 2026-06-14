from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StockCandidate:
    code: str
    name: str
    board: str
    price: float
    pct_change: float
    index_pct_change: float
    current_volume: int
    same_time_volumes_5d: List[int]
    turnover_rate: float
    float_market_cap_billion: float
    recent_daily_volumes: List[int]
    projected_daily_volume: int
    ma5: float
    ma10: float
    ma20: float
    ma60: float
    ma60_prev: float
    intraday_above_avg_ratio: float
    recovered_after_avg_break: bool
    theme: str = ""
    theme_rank: Optional[int] = None
    has_hot_theme: bool = False
    pressure_distance_pct: Optional[float] = None
    upper_shadow_recent: bool = False
    is_st: bool = False
    is_suspended: bool = False
    listing_days: int = 0
    limit_up_seal_strength: Optional[float] = None
    data_source: str = ""
    main_net_inflow: Optional[float] = None


@dataclass(frozen=True)
class Signal:
    code: str
    name: str
    level: str
    score: float
    signal_type: str
    reasons: List[str]
    metrics: Dict[str, float]
    theme: str = ""
    data_source: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "code": self.code,
            "name": self.name,
            "level": self.level,
            "score": round(self.score, 2),
            "signal_type": self.signal_type,
            "reasons": self.reasons,
            "metrics": {key: round(value, 4) for key, value in self.metrics.items()},
            "theme": self.theme,
            "data_source": self.data_source,
        }


@dataclass(frozen=True)
class EvaluationResult:
    candidate: StockCandidate
    passed: bool
    metrics: Dict[str, float] = field(default_factory=dict)
    reason_code: str = ""
    reason: str = ""
    signal: Optional[Signal] = None
