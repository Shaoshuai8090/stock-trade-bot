from dataclasses import dataclass
from statistics import mean
from typing import Iterable, List, Optional, Tuple

from trade_signal_tool.models import EvaluationResult, Signal, StockCandidate


@dataclass(frozen=True)
class AfterCloseConfig:
    min_float_market_cap_billion: float = 50.0
    excluded_code_prefixes: Tuple[str, ...] = ("68",)
    max_intraday_gain_pct: float = 8.0
    max_ma5_gap_pct: float = 5.0
    max_ma10_gap_pct: float = 8.0
    max_float_market_cap_billion: float = 400.0
    min_listing_days: int = 60
    watch_threshold: float = 70.0
    strong_threshold: float = 80.0
    min_amount_volume: int = 0


class AfterCloseStrategy:
    """收盘后次日观察池策略。

    Compared with the intraday strategy, this keeps fewer hard rejections and
    lets pressure, volume, and theme quality affect score instead of deleting
    otherwise valid candidates too early.
    """

    def __init__(self, config: Optional[AfterCloseConfig] = None):
        self.config = config or AfterCloseConfig()

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
            return EvaluationResult(candidate=candidate, passed=False, metrics=metrics, reason_code=code, reason=reason)

        score, reasons = self._score(candidate, metrics)
        if score < self.config.watch_threshold:
            return EvaluationResult(
                candidate=candidate,
                passed=False,
                metrics=metrics,
                reason_code="score_below_threshold",
                reason="收盘候选池评分低于阈值",
            )

        level = "strong" if score >= self.config.strong_threshold else "watch"
        signal = Signal(
            code=candidate.code,
            name=candidate.name,
            level=level,
            score=score,
            signal_type="收盘次日观察池",
            reasons=reasons,
            metrics=metrics,
            theme=candidate.theme,
            data_source=candidate.data_source,
        )
        return EvaluationResult(candidate=candidate, passed=True, metrics=metrics, signal=signal)

    def _metrics(self, candidate: StockCandidate) -> dict:
        avg_volume = mean(candidate.same_time_volumes_5d) if candidate.same_time_volumes_5d else 0
        volume_ratio = candidate.current_volume / avg_volume if avg_volume else 0
        ma60_slope_pct = ((candidate.ma60 - candidate.ma60_prev) / candidate.ma60_prev * 100) if candidate.ma60_prev else 0
        ma5_gap_pct = self._gap_pct(candidate.price, candidate.ma5)
        ma10_gap_pct = self._gap_pct(candidate.price, candidate.ma10)
        ma20_gap_pct = self._gap_pct(candidate.price, candidate.ma20)
        support = candidate.ma5 if ma5_gap_pct <= self.config.max_ma5_gap_pct else candidate.ma10
        buy_zone_low = support * 0.995 if support > 0 else 0.0
        buy_zone_high = support * 1.015 if support > 0 else 0.0
        return {
            "volume_ratio": volume_ratio,
            "turnover_rate": candidate.turnover_rate,
            "float_market_cap_billion": candidate.float_market_cap_billion,
            "intraday_relative_strength": candidate.pct_change - candidate.index_pct_change,
            "intraday_above_avg_ratio": candidate.intraday_above_avg_ratio,
            "ma5": candidate.ma5,
            "ma10": candidate.ma10,
            "ma20": candidate.ma20,
            "ma5_gap_pct": ma5_gap_pct,
            "ma10_gap_pct": ma10_gap_pct,
            "ma20_gap_pct": ma20_gap_pct,
            "buy_zone_low": buy_zone_low,
            "buy_zone_high": buy_zone_high,
            "stop_loss": candidate.ma20 * 0.97 if candidate.ma20 > 0 else 0.0,
            "ma60_slope_pct": ma60_slope_pct,
            "pressure_distance_pct": candidate.pressure_distance_pct or 999.0,
            "turnover_min": self._turnover_range(candidate.float_market_cap_billion)[0],
            "turnover_max": self._turnover_range(candidate.float_market_cap_billion)[1],
            "main_net_inflow": candidate.main_net_inflow or 0.0,
        }

    def _hard_rejection(self, candidate: StockCandidate, metrics: dict) -> Optional[Tuple[str, str]]:
        cfg = self.config
        if candidate.code.startswith(cfg.excluded_code_prefixes):
            return "excluded_code_prefix", "账户不可交易的板块不进入候选池"
        if candidate.pct_change > cfg.max_intraday_gain_pct:
            return "overextended_intraday_gain", "当日涨幅过大，收盘后不追高"
        if metrics["ma5_gap_pct"] > cfg.max_ma5_gap_pct and metrics["ma10_gap_pct"] > cfg.max_ma10_gap_pct:
            return "poor_buy_point", "价格远离 MA5/MA10，次日买点不友好"
        if candidate.is_st:
            return "st_stock", "ST 股票不进入候选池"
        if candidate.is_suspended:
            return "suspended", "停牌股票不进入候选池"
        if candidate.listing_days < cfg.min_listing_days:
            return "new_listing", "上市时间不足，历史样本不稳定"
        if not (cfg.min_float_market_cap_billion <= candidate.float_market_cap_billion <= cfg.max_float_market_cap_billion):
            return "market_cap_out_of_range", "流通市值不在 50 亿-400 亿候选区间"
        turnover_min, turnover_max = self._turnover_range(candidate.float_market_cap_billion)
        if not (turnover_min <= candidate.turnover_rate <= turnover_max):
            return "turnover_out_of_dynamic_range", "换手率不在当前市值对应的健康区间"
        if candidate.price < candidate.ma20:
            return "under_ma20", "收盘价仍在 20 日均线下方"
        return None

    def _score(self, candidate: StockCandidate, metrics: dict) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []

        market_score = self._market_score(candidate, metrics)
        score += market_score
        if market_score >= 10:
            reasons.append("个股强于指数，市场环境项通过")

        theme_score = self._theme_score(candidate)
        score += theme_score
        if candidate.has_hot_theme:
            reasons.append("叠加强势题材")
        else:
            reasons.append("未接入题材强度，按中性题材评分")

        fund_score, fund_reasons = self._fund_score(candidate, metrics)
        score += fund_score
        reasons.extend(fund_reasons)

        trend_score = self._trend_score(candidate, metrics)
        score += trend_score
        if trend_score >= 14:
            reasons.append("趋势结构较好，收盘价站上 MA20")

        volume_score = self._volume_score(candidate, metrics)
        score += volume_score
        if volume_score >= 12:
            reasons.append("量价配合较好，成交量温和放大")

        risk_score, risk_reasons = self._risk_score(candidate, metrics)
        score += risk_score
        reasons.extend(risk_reasons)

        liquidity_score = self._liquidity_score(candidate, metrics)
        score += liquidity_score
        if liquidity_score >= 7:
            reasons.append("市值和换手匹配短线候选区间")

        buy_point_score = self._buy_point_score(metrics)
        score += buy_point_score
        if buy_point_score >= 4:
            reasons.append("买点距离均线支撑较近，适合次日等回踩确认")

        return min(score, 100.0), reasons

    def _market_score(self, candidate: StockCandidate, metrics: dict) -> float:
        relative = metrics["intraday_relative_strength"]
        if relative >= 3:
            return 15
        if relative >= 1:
            return 12
        if relative >= 0:
            return 9
        return 5

    def _theme_score(self, candidate: StockCandidate) -> float:
        if not candidate.has_hot_theme:
            return 8.0
        if candidate.theme_rank is None:
            return 16.0
        if candidate.theme_rank <= 3:
            return 25.0
        if candidate.theme_rank <= 10:
            return 20.0
        return 14.0

    def _fund_score(self, candidate: StockCandidate, metrics: dict) -> Tuple[float, List[str]]:
        inflow = metrics.get("main_net_inflow", 0.0)
        if inflow >= 30_000_000:
            return 5.0, ["主力资金净流入，资金面加分"]
        if inflow > 0:
            return 3.0, ["主力资金小幅净流入"]
        if inflow <= -30_000_000:
            return -4.0, ["主力资金净流出，资金面扣分"]
        if inflow < 0:
            return -2.0, ["主力资金小幅净流出"]
        return 0.0, []

    def _trend_score(self, candidate: StockCandidate, metrics: dict) -> float:
        score = 6.0
        if candidate.price > candidate.ma5:
            score += 4
        if candidate.ma5 > candidate.ma10:
            score += 4
        if candidate.ma10 >= candidate.ma20:
            score += 3
        if candidate.ma20 >= candidate.ma60:
            score += 2
        if metrics["ma60_slope_pct"] >= 0:
            score += 1
        return min(score, 20.0)

    def _volume_score(self, candidate: StockCandidate, metrics: dict) -> float:
        score = min(metrics["volume_ratio"] / 1.8, 1.0) * 8
        if candidate.projected_daily_volume > mean(candidate.recent_daily_volumes):
            score += 6
        volumes = list(candidate.recent_daily_volumes) + [candidate.projected_daily_volume]
        rising_pairs = sum(1 for previous, current in zip(volumes, volumes[1:]) if current > previous)
        score += rising_pairs / max(len(volumes) - 1, 1) * 6
        return min(score, 20.0)

    def _risk_score(self, candidate: StockCandidate, metrics: dict) -> Tuple[float, List[str]]:
        pressure = metrics["pressure_distance_pct"]
        reasons = []
        if pressure >= 8:
            score = 10.0
            reasons.append("上方空间相对充足")
        elif pressure >= 5:
            score = 8.0
            reasons.append("距离前高不远，次日观察承接")
        elif pressure >= 3:
            score = 6.0
            reasons.append("接近前高，避免追高")
        else:
            score = 3.0
            reasons.append("接近前高，作为风险扣分而非直接剔除")
        if candidate.upper_shadow_recent:
            score -= 3
            reasons.append("近期上影线偏长，抛压扣分")
        if candidate.pct_change > 8 and (candidate.limit_up_seal_strength or 0) < 0.5:
            score -= 2
            reasons.append("涨幅较大但封单质量不足，次日不追高")
        return max(score, 0.0), reasons

    def _liquidity_score(self, candidate: StockCandidate, metrics: dict) -> float:
        cap = candidate.float_market_cap_billion
        cap_score = 5.0 if 80 <= cap <= 220 else 3.5
        turnover_min, turnover_max = self._turnover_range(cap)
        midpoint = (turnover_min + turnover_max) / 2
        half_range = max((turnover_max - turnover_min) / 2, 1)
        turnover_score = max(0.0, 5 - abs(candidate.turnover_rate - midpoint) / half_range * 2)
        return min(cap_score + turnover_score, 10.0)

    def _buy_point_score(self, metrics: dict) -> float:
        ma5_gap = metrics["ma5_gap_pct"]
        ma10_gap = metrics["ma10_gap_pct"]
        if ma5_gap <= 2:
            return 6.0
        if ma5_gap <= self.config.max_ma5_gap_pct:
            return 4.0
        if ma10_gap <= self.config.max_ma10_gap_pct:
            return 2.0
        return 0.0

    def _gap_pct(self, price: float, reference: float) -> float:
        if reference <= 0:
            return 999.0
        return (price - reference) / reference * 100

    def _turnover_range(self, float_market_cap_billion: float) -> Tuple[float, float]:
        if float_market_cap_billion < 100:
            return 6.0, 18.0
        if float_market_cap_billion < 200:
            return 4.0, 14.0
        return 3.0, 10.0
