from dataclasses import dataclass
from statistics import mean
from typing import Iterable, List, Optional, Tuple

from trade_signal_tool.models import EvaluationResult, Signal, StockCandidate


@dataclass(frozen=True)
class StrategyConfig:
    min_volume_ratio: float = 1.0
    min_turnover_rate: float = 5.0
    max_turnover_rate: float = 10.0
    min_float_market_cap_billion: float = 50.0
    max_float_market_cap_billion: float = 200.0
    min_listing_days: int = 60
    min_intraday_above_avg_ratio: float = 0.7
    min_pressure_distance_pct: float = 5.0
    watch_threshold: float = 75.0
    strong_threshold: float = 85.0


class SignalStrategy:
    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig()

    def scan(self, candidates: Iterable[StockCandidate]) -> List[Signal]:
        signals = []
        for candidate in candidates:
            result = self.evaluate(candidate)
            if result.passed and result.signal is not None:
                signals.append(result.signal)
        return sorted(signals, key=lambda signal: signal.score, reverse=True)

    def evaluate(self, candidate: StockCandidate) -> EvaluationResult:
        metrics = self._metrics(candidate)
        rejection = self._hard_rejection(candidate, metrics)
        if rejection is not None:
            code, reason = rejection
            return EvaluationResult(
                candidate=candidate,
                passed=False,
                metrics=metrics,
                reason_code=code,
                reason=reason,
            )

        score, reasons = self._score(candidate, metrics)
        if score < self.config.watch_threshold:
            return EvaluationResult(
                candidate=candidate,
                passed=False,
                metrics=metrics,
                reason_code="score_below_threshold",
                reason="综合评分低于观察阈值",
            )

        level = "strong" if score >= self.config.strong_threshold else "watch"
        signal = Signal(
            code=candidate.code,
            name=candidate.name,
            level=level,
            score=score,
            signal_type=self._signal_type(candidate, metrics),
            reasons=reasons,
            metrics=metrics,
            theme=candidate.theme,
        )
        return EvaluationResult(candidate=candidate, passed=True, metrics=metrics, signal=signal)

    def _metrics(self, candidate: StockCandidate) -> dict:
        avg_same_time_volume = mean(candidate.same_time_volumes_5d) if candidate.same_time_volumes_5d else 0
        volume_ratio = candidate.current_volume / avg_same_time_volume if avg_same_time_volume else 0
        ma60_slope_pct = ((candidate.ma60 - candidate.ma60_prev) / candidate.ma60_prev * 100) if candidate.ma60_prev else 0
        return {
            "volume_ratio": volume_ratio,
            "turnover_rate": candidate.turnover_rate,
            "float_market_cap_billion": candidate.float_market_cap_billion,
            "intraday_relative_strength": candidate.pct_change - candidate.index_pct_change,
            "intraday_above_avg_ratio": candidate.intraday_above_avg_ratio,
            "ma60_slope_pct": ma60_slope_pct,
            "pressure_distance_pct": candidate.pressure_distance_pct or 999.0,
        }

    def _hard_rejection(self, candidate: StockCandidate, metrics: dict) -> Optional[Tuple[str, str]]:
        cfg = self.config
        if candidate.is_st:
            return "st_stock", "ST 股票不进入基础股票池"
        if candidate.is_suspended:
            return "suspended", "停牌股票不进入基础股票池"
        if candidate.listing_days < cfg.min_listing_days:
            return "new_listing", "上市时间不足，历史样本不稳定"
        if metrics["volume_ratio"] < cfg.min_volume_ratio:
            return "volume_ratio_below_one", "量比低于 1，交易活跃度不足"
        if not (cfg.min_turnover_rate <= candidate.turnover_rate <= cfg.max_turnover_rate):
            return "turnover_out_of_range", "换手率不在 5%-10% 区间"
        if not (cfg.min_float_market_cap_billion <= candidate.float_market_cap_billion <= cfg.max_float_market_cap_billion):
            return "market_cap_out_of_range", "流通市值不在 50 亿-200 亿区间"
        if candidate.price < candidate.ma20 or candidate.price < candidate.ma60:
            return "under_important_moving_average", "价格仍压在 20 日或 60 日重要均线下方"
        if candidate.pressure_distance_pct is not None and candidate.pressure_distance_pct < cfg.min_pressure_distance_pct:
            return "near_overhead_pressure", "上方压力位过近"
        if candidate.upper_shadow_recent:
            return "recent_upper_shadow", "近期长上影显示上方抛压较重"
        if candidate.pct_change <= candidate.index_pct_change:
            return "not_outperforming_index", "个股没有跑赢对应指数"
        if candidate.intraday_above_avg_ratio < cfg.min_intraday_above_avg_ratio:
            return "weak_intraday_position", "分时多数时间未能运行在均价线上方"
        return None

    def _score(self, candidate: StockCandidate, metrics: dict) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []

        ratio_score = min(metrics["volume_ratio"] / 3.0, 1.0) * 15
        score += ratio_score
        reasons.append("量比放大，当前交易活跃度高于过去5日同刻均值")

        turnover_score = max(0.0, 10 - abs(candidate.turnover_rate - 7.5) / 2.5 * 2)
        score += turnover_score
        reasons.append("换手率处于5%-10%的健康区间")

        cap_midpoint = 100.0
        cap_score = max(7.0, 10 - abs(candidate.float_market_cap_billion - cap_midpoint) / 100)
        score += cap_score
        reasons.append("流通市值处于50亿-200亿的弹性区间")

        volume_score = self._volume_staircase_score(candidate)
        score += volume_score
        if volume_score >= 15:
            reasons.append("成交量呈台阶式放大")

        ma_score = self._moving_average_score(candidate, metrics)
        score += ma_score
        if ma_score >= 20:
            reasons.append("均线多头发散，价格站上重要均线")

        intraday_score = self._intraday_score(candidate, metrics)
        score += intraday_score
        reasons.append("分时强于大盘且多数时间在均价线上方")

        theme_score = self._theme_score(candidate)
        score += theme_score
        if theme_score > 0:
            reasons.append("叠加当下热点题材")

        return min(score, 100.0), reasons

    def _volume_staircase_score(self, candidate: StockCandidate) -> float:
        volumes = list(candidate.recent_daily_volumes) + [candidate.projected_daily_volume]
        if len(volumes) < 2:
            return 0.0
        rising_pairs = sum(1 for previous, current in zip(volumes, volumes[1:]) if current > previous)
        pair_score = rising_pairs / (len(volumes) - 1) * 14
        above_recent_avg = 6 if candidate.projected_daily_volume > mean(candidate.recent_daily_volumes) else 0
        return pair_score + above_recent_avg

    def _moving_average_score(self, candidate: StockCandidate, metrics: dict) -> float:
        score = 0.0
        if candidate.ma5 > candidate.ma10:
            score += 5
        if candidate.ma10 > candidate.ma20:
            score += 5
        if candidate.ma20 > candidate.ma60:
            score += 5
        if candidate.price > candidate.ma5:
            score += 5
        if metrics["ma60_slope_pct"] > 0:
            score += 5
        return score

    def _intraday_score(self, candidate: StockCandidate, metrics: dict) -> float:
        score = min(metrics["intraday_relative_strength"] / 4.0, 1.0) * 6
        score += min(candidate.intraday_above_avg_ratio / 0.9, 1.0) * 7
        if candidate.recovered_after_avg_break:
            score += 2
        return min(score, 15.0)

    def _theme_score(self, candidate: StockCandidate) -> float:
        if not candidate.has_hot_theme:
            return 0.0
        if candidate.theme_rank is None:
            return 3.0
        if candidate.theme_rank <= 3:
            return 5.0
        if candidate.theme_rank <= 10:
            return 4.0
        return 2.0

    def _signal_type(self, candidate: StockCandidate, metrics: dict) -> str:
        if candidate.has_hot_theme and metrics["intraday_above_avg_ratio"] >= 0.8:
            return "题材共振型"
        if self._volume_staircase_score(candidate) >= 15 and self._moving_average_score(candidate, metrics) >= 20:
            return "强势突破型"
        return "分时承接型"
