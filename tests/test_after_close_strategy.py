import unittest

from trade_signal_tool.after_close_strategy import AfterCloseConfig, AfterCloseStrategy
from trade_signal_tool.models import StockCandidate


def candidate(**overrides):
    data = {
        "code": "300001",
        "name": "示例科技",
        "board": "创业板",
        "price": 18.3,
        "pct_change": 4.2,
        "index_pct_change": 1.0,
        "current_volume": 12_000_000,
        "same_time_volumes_5d": [8_000_000, 8_500_000, 8_200_000, 8_300_000, 8_100_000],
        "turnover_rate": 9.0,
        "float_market_cap_billion": 88.0,
        "recent_daily_volumes": [8_000_000, 9_000_000, 10_000_000],
        "projected_daily_volume": 12_000_000,
        "ma5": 17.8,
        "ma10": 17.1,
        "ma20": 16.2,
        "ma60": 20.0,
        "ma60_prev": 20.1,
        "intraday_above_avg_ratio": 0.55,
        "recovered_after_avg_break": False,
        "theme": "机器人",
        "theme_rank": 4,
        "has_hot_theme": True,
        "pressure_distance_pct": 2.2,
        "upper_shadow_recent": False,
        "is_st": False,
        "is_suspended": False,
        "listing_days": 360,
        "limit_up_seal_strength": 0.2,
    }
    data.update(overrides)
    return StockCandidate(**data)


class AfterCloseStrategyTest(unittest.TestCase):
    def test_accepts_candidate_above_ma20_without_requiring_ma60_breakout(self):
        result = AfterCloseStrategy().evaluate(candidate())

        self.assertTrue(result.passed)
        self.assertNotEqual(result.reason_code, "under_important_moving_average")
        self.assertIn("次日观察池", result.signal.signal_type)

    def test_near_pressure_is_penalty_not_hard_rejection(self):
        near = AfterCloseStrategy().evaluate(candidate(pressure_distance_pct=2.0))
        far = AfterCloseStrategy().evaluate(candidate(pressure_distance_pct=12.0))

        self.assertTrue(near.passed)
        self.assertTrue(far.passed)
        self.assertLess(near.signal.score, far.signal.score)
        self.assertIn("接近前高", " ".join(near.signal.reasons))

    def test_dynamic_turnover_range_depends_on_market_cap(self):
        mid_cap_ok = AfterCloseStrategy().evaluate(candidate(float_market_cap_billion=250, turnover_rate=9.5))
        mid_cap_hot = AfterCloseStrategy().evaluate(candidate(float_market_cap_billion=250, turnover_rate=12.5))

        self.assertTrue(mid_cap_ok.passed)
        self.assertFalse(mid_cap_hot.passed)
        self.assertEqual(mid_cap_hot.reason_code, "turnover_out_of_dynamic_range")

    def test_volume_ratio_below_one_is_scored_not_hard_rejected(self):
        result = AfterCloseStrategy(AfterCloseConfig(watch_threshold=60)).evaluate(
            candidate(
                current_volume=7_000_000,
                same_time_volumes_5d=[8_000_000, 8_500_000, 8_200_000, 8_300_000, 8_100_000],
                recent_daily_volumes=[6_500_000, 6_800_000, 6_900_000],
                projected_daily_volume=7_000_000,
            )
        )

        self.assertTrue(result.passed)
        self.assertNotEqual(result.reason_code, "volume_ratio_below_one")

    def test_main_net_inflow_boosts_score_without_hard_filtering(self):
        neutral = AfterCloseStrategy().evaluate(candidate(main_net_inflow=None))
        inflow = AfterCloseStrategy().evaluate(candidate(main_net_inflow=50_000_000))
        outflow = AfterCloseStrategy().evaluate(candidate(main_net_inflow=-50_000_000))

        self.assertTrue(neutral.passed)
        self.assertTrue(inflow.passed)
        self.assertTrue(outflow.passed)
        self.assertGreater(inflow.signal.score, neutral.signal.score)
        self.assertLess(outflow.signal.score, neutral.signal.score)
        self.assertIn("主力资金净流入", " ".join(inflow.signal.reasons))

    def test_signal_carries_realtime_data_source(self):
        result = AfterCloseStrategy().evaluate(candidate(data_source="tencent"))

        self.assertTrue(result.passed)
        self.assertEqual(result.signal.data_source, "tencent")
        self.assertEqual(result.signal.to_dict()["data_source"], "tencent")

    def test_rejects_price_under_ma20_for_after_close_pool(self):
        result = AfterCloseStrategy().evaluate(candidate(price=15.8))

        self.assertFalse(result.passed)
        self.assertEqual(result.reason_code, "under_ma20")


if __name__ == "__main__":
    unittest.main()
