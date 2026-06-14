import unittest

from trade_signal_tool.models import StockCandidate
from trade_signal_tool.strategy import SignalStrategy, StrategyConfig


def strong_candidate(**overrides):
    data = {
        "code": "300001",
        "name": "示例科技",
        "board": "创业板",
        "price": 18.32,
        "pct_change": 5.2,
        "index_pct_change": 1.1,
        "current_volume": 3_200_000,
        "same_time_volumes_5d": [1_200_000, 1_350_000, 1_280_000, 1_310_000, 1_260_000],
        "turnover_rate": 6.8,
        "float_market_cap_billion": 88.0,
        "recent_daily_volumes": [8_000_000, 9_300_000, 10_800_000],
        "projected_daily_volume": 13_500_000,
        "ma5": 17.2,
        "ma10": 16.5,
        "ma20": 15.7,
        "ma60": 14.9,
        "ma60_prev": 14.6,
        "intraday_above_avg_ratio": 0.86,
        "recovered_after_avg_break": True,
        "theme": "机器人",
        "theme_rank": 3,
        "has_hot_theme": True,
        "pressure_distance_pct": 12.0,
        "upper_shadow_recent": False,
        "is_st": False,
        "is_suspended": False,
        "listing_days": 360,
        "limit_up_seal_strength": 0.62,
    }
    data.update(overrides)
    return StockCandidate(**data)


class SignalStrategyTest(unittest.TestCase):
    def test_rejects_volume_ratio_below_one(self):
        candidate = strong_candidate(
            current_volume=900_000,
            same_time_volumes_5d=[1_000_000, 1_050_000, 1_020_000, 1_010_000, 1_030_000],
        )

        result = SignalStrategy().evaluate(candidate)

        self.assertFalse(result.passed)
        self.assertEqual(result.reason_code, "volume_ratio_below_one")
        self.assertAlmostEqual(result.metrics["volume_ratio"], 0.88, places=2)

    def test_rejects_turnover_outside_five_to_ten_percent(self):
        low = SignalStrategy().evaluate(strong_candidate(turnover_rate=4.9))
        high = SignalStrategy().evaluate(strong_candidate(turnover_rate=10.1))

        self.assertFalse(low.passed)
        self.assertEqual(low.reason_code, "turnover_out_of_range")
        self.assertFalse(high.passed)
        self.assertEqual(high.reason_code, "turnover_out_of_range")

    def test_accepts_strong_candidate_with_confluence(self):
        result = SignalStrategy().evaluate(strong_candidate())

        self.assertTrue(result.passed)
        self.assertEqual(result.signal.level, "strong")
        self.assertGreaterEqual(result.signal.score, 85)
        self.assertIn("量比", " ".join(result.signal.reasons))
        self.assertIn("均线多头", " ".join(result.signal.reasons))

    def test_rejects_price_under_important_moving_average(self):
        result = SignalStrategy().evaluate(strong_candidate(price=14.7))

        self.assertFalse(result.passed)
        self.assertEqual(result.reason_code, "under_important_moving_average")

    def test_scan_ranks_passing_signals_by_score(self):
        strategy = SignalStrategy(StrategyConfig(watch_threshold=70, strong_threshold=85))
        better = strong_candidate(code="300001", name="更强科技", intraday_above_avg_ratio=0.95)
        weaker = strong_candidate(
            code="600001",
            name="观察股份",
            current_volume=1_650_000,
            projected_daily_volume=11_000_000,
            has_hot_theme=False,
            theme_rank=None,
            intraday_above_avg_ratio=0.72,
        )
        rejected = strong_candidate(code="000001", name="低换手", turnover_rate=3.2)

        signals = strategy.scan([weaker, rejected, better])

        self.assertEqual([signal.code for signal in signals], ["300001", "600001"])
        self.assertEqual(signals[0].level, "strong")


if __name__ == "__main__":
    unittest.main()
