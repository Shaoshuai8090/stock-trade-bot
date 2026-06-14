import unittest

from trade_signal_tool.models import StockCandidate
from trade_signal_tool.providers.tencent_provider import TencentRealtimeProvider


def candidate(**overrides):
    data = {
        "code": "300001",
        "name": "旧名称",
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


def tencent_line(symbol="sz300001"):
    fields = [""] * 88
    fields[0] = "1"
    fields[1] = "示例科技"
    fields[2] = "300001"
    fields[3] = "18.32"
    fields[4] = "17.42"
    fields[5] = "17.80"
    fields[30] = "20260612150000"
    fields[31] = "0.90"
    fields[32] = "5.17"
    fields[33] = "18.60"
    fields[34] = "17.70"
    fields[36] = "320000"
    fields[37] = "58000"
    fields[38] = "6.80"
    fields[44] = "120.0"
    fields[45] = "88.0"
    return f'v_{symbol}="{"~".join(fields)}";'


class TencentRealtimeProviderTest(unittest.TestCase):
    def test_fetch_records_parses_tencent_batch_response(self):
        captured = {}

        class FakeResponse:
            def read(self):
                return tencent_line().encode("gbk")

        def fake_urlopen(url, timeout):
            captured["url"] = url
            captured["timeout"] = timeout
            return FakeResponse()

        provider = TencentRealtimeProvider(urlopen=fake_urlopen, timeout_seconds=3)

        records = provider.fetch_records(["300001"])

        self.assertIn("q=sz300001", captured["url"])
        self.assertEqual(captured["timeout"], 3)
        self.assertEqual(records["300001"]["name"], "示例科技")
        self.assertEqual(records["300001"]["current_volume"], 320_000)
        self.assertAlmostEqual(records["300001"]["turnover_rate"], 6.8)
        self.assertAlmostEqual(records["300001"]["float_market_cap_billion"], 88.0)

    def test_refresh_candidates_replaces_realtime_fields_and_marks_source(self):
        class FakeResponse:
            def read(self):
                return tencent_line().encode("gbk")

        provider = TencentRealtimeProvider(urlopen=lambda url, timeout: FakeResponse())

        refreshed = provider.refresh_candidates([candidate()])

        self.assertEqual(len(refreshed), 1)
        self.assertEqual(refreshed[0].name, "示例科技")
        self.assertAlmostEqual(refreshed[0].price, 18.32)
        self.assertAlmostEqual(refreshed[0].pct_change, 5.17)
        self.assertEqual(refreshed[0].current_volume, 320_000)
        self.assertAlmostEqual(refreshed[0].turnover_rate, 6.8)
        self.assertAlmostEqual(refreshed[0].float_market_cap_billion, 88.0)
        self.assertEqual(refreshed[0].data_source, "tencent")


if __name__ == "__main__":
    unittest.main()
