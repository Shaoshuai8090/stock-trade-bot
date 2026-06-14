import unittest

from trade_signal_tool.models import StockCandidate
from trade_signal_tool.providers.a_stock_provider import AStockDataProvider


def candidate(**overrides):
    data = {
        "code": "300001",
        "name": "示例科技",
        "board": "创业板",
        "price": 17.0,
        "pct_change": 1.0,
        "index_pct_change": 0.0,
        "current_volume": 100_000,
        "same_time_volumes_5d": [80_000, 90_000, 85_000, 88_000, 82_000],
        "turnover_rate": 3.0,
        "float_market_cap_billion": 60.0,
        "recent_daily_volumes": [700_000, 800_000, 900_000],
        "projected_daily_volume": 950_000,
        "ma5": 16.8,
        "ma10": 16.2,
        "ma20": 15.8,
        "ma60": 15.0,
        "ma60_prev": 14.8,
        "intraday_above_avg_ratio": 1.0,
        "recovered_after_avg_break": True,
        "listing_days": 300,
    }
    data.update(overrides)
    return StockCandidate(**data)


class FakeBaseProvider:
    def __init__(self):
        self.calls = []

    def fetch_candidates(self, max_candidates, enrich_limit):
        self.calls.append((max_candidates, enrich_limit))
        return [candidate()]

    def trading_days(self):
        return ["20260612"]


class FakeTencentProvider:
    def __init__(self):
        self.received = []

    def refresh_candidates(self, candidates):
        self.received = list(candidates)
        return [candidate(price=18.32, pct_change=5.17, data_source="tencent")]


class AStockDataProviderTest(unittest.TestCase):
    def test_fetch_candidates_uses_base_provider_then_tencent_refresh(self):
        base = FakeBaseProvider()
        tencent = FakeTencentProvider()
        provider = AStockDataProvider(base_provider=base, realtime_provider=tencent)

        candidates = provider.fetch_candidates(max_candidates=50, enrich_limit=3)

        self.assertEqual(base.calls, [(50, 3)])
        self.assertEqual(tencent.received[0].code, "300001")
        self.assertEqual(candidates[0].price, 18.32)
        self.assertEqual(candidates[0].data_source, "tencent")

    def test_fetch_candidates_keeps_base_candidates_if_tencent_refresh_fails(self):
        class FailingTencentProvider:
            def refresh_candidates(self, candidates):
                raise RuntimeError("tencent blocked")

        provider = AStockDataProvider(base_provider=FakeBaseProvider(), realtime_provider=FailingTencentProvider())

        candidates = provider.fetch_candidates(max_candidates=50, enrich_limit=3)

        self.assertEqual(candidates[0].price, 17.0)
        self.assertEqual(candidates[0].data_source, "akshare")


if __name__ == "__main__":
    unittest.main()
