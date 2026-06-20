import unittest
from datetime import date

from trade_signal_tool.providers.akshare_provider import AkShareProvider


class FakeFrame:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        self.assert_orient = orient
        return self.records


class FakeAkshare:
    def __init__(self):
        self.hist_calls = []
        self.minute_calls = []

    def stock_zh_a_spot_em(self):
        return FakeFrame(
            [
                {
                    "代码": "300001",
                    "名称": "示例科技",
                    "最新价": 18.32,
                    "涨跌幅": 5.2,
                    "成交量": 3_200_000,
                    "量比": 2.5,
                    "换手率": 6.8,
                    "流通市值": 8_800_000_000,
                },
                {
                    "代码": "000001",
                    "名称": "低量比",
                    "最新价": 9.12,
                    "涨跌幅": 1.2,
                    "成交量": 800_000,
                    "量比": 0.8,
                    "换手率": 6.2,
                    "流通市值": 9_600_000_000,
                },
            ]
        )

    def stock_zh_a_hist(self, symbol, period, start_date, end_date, adjust):
        self.hist_calls.append(symbol)
        rows = []
        for idx in range(70):
            close = 10 + idx * 0.1
            rows.append(
                {
                    "日期": f"2026-03-{(idx % 28) + 1:02d}",
                    "股票代码": symbol,
                    "开盘": close - 0.1,
                    "收盘": close,
                    "最高": close + 0.2,
                    "最低": close - 0.2,
                    "成交量": 1_000_000 + idx * 50_000,
                    "换手率": 6.8,
                }
            )
        return FakeFrame(rows)

    def stock_zh_a_hist_min_em(self, symbol, start_date, end_date, period, adjust):
        self.minute_calls.append(symbol)
        return FakeFrame(
            [
                {"时间": "2026-06-03 09:30:00", "收盘": 18.1, "均价": 18.0},
                {"时间": "2026-06-03 09:31:00", "收盘": 18.3, "均价": 18.1},
                {"时间": "2026-06-03 09:32:00", "收盘": 18.2, "均价": 18.25},
            ]
        )


class FailingSpotAkshare(FakeAkshare):
    def stock_zh_a_spot_em(self):
        raise RuntimeError("remote disconnected")


class PartiallyFailingDailyAkshare(FakeAkshare):
    def stock_zh_a_spot_em(self):
        return FakeFrame(
            [
                {
                    "代码": "300001",
                    "名称": "坏日线",
                    "最新价": 18.32,
                    "涨跌幅": 5.2,
                    "成交量": 3_200_000,
                    "量比": 2.5,
                    "换手率": 6.8,
                    "流通市值": 8_800_000_000,
                },
                {
                    "代码": "300002",
                    "名称": "好日线",
                    "最新价": 18.32,
                    "涨跌幅": 5.2,
                    "成交量": 3_200_000,
                    "量比": 2.5,
                    "换手率": 6.8,
                    "流通市值": 8_800_000_000,
                },
            ]
        )

    def stock_zh_a_hist(self, symbol, period, start_date, end_date, adjust):
        if symbol == "300001":
            raise RuntimeError("daily disconnected")
        return super().stock_zh_a_hist(symbol, period, start_date, end_date, adjust)


class SinaDailyFallbackAkshare(FakeAkshare):
    def stock_zh_a_hist(self, symbol, period, start_date, end_date, adjust):
        raise RuntimeError("eastmoney daily disconnected")

    def stock_zh_a_daily(self, symbol, start_date, end_date, adjust):
        rows = []
        for idx in range(70):
            close = 10 + idx * 0.1
            rows.append(
                {
                    "date": f"2026-03-{(idx % 28) + 1:02d}",
                    "open": close - 0.1,
                    "high": close + 0.2,
                    "low": close - 0.2,
                    "close": close,
                    "volume": 100_000_000 + idx * 5_000_000,
                    "amount": 1_000_000_000,
                    "outstanding_share": 1_000_000_000,
                    "turnover": 0.068,
                }
            )
        self.sina_daily_symbol = symbol
        return FakeFrame(rows)


class AkshareSinaSpotFallbackAkshare(SinaDailyFallbackAkshare):
    def stock_zh_a_spot_em(self):
        raise RuntimeError("eastmoney spot disconnected")

    def stock_zh_a_spot(self):
        return FakeFrame(
            [
                {
                    "代码": "sz300001",
                    "名称": "示例科技",
                    "最新价": 18.32,
                    "涨跌幅": 5.2,
                    "成交量": 320_000_000,
                    "成交额": 5_800_000_000,
                }
            ]
        )


class LowRiskMixedBoardSpotAkshare(SinaDailyFallbackAkshare):
    def stock_zh_a_spot_em(self):
        raise RuntimeError("eastmoney spot disconnected")

    def stock_zh_a_spot(self):
        return FakeFrame(
            [
                {
                    "代码": "bj920001",
                    "名称": "北证样本",
                    "最新价": 12.0,
                    "涨跌幅": 7.0,
                    "成交量": 600_000_000,
                    "成交额": 7_200_000_000,
                },
                {
                    "代码": "sz300001",
                    "名称": "示例科技",
                    "最新价": 18.32,
                    "涨跌幅": 5.2,
                    "成交量": 320_000_000,
                    "成交额": 5_800_000_000,
                },
            ]
        )


class LowRiskMissingLiquidityRankAkshare(SinaDailyFallbackAkshare):
    def stock_zh_a_spot_em(self):
        raise RuntimeError("eastmoney spot disconnected")

    def stock_zh_a_spot(self):
        return FakeFrame(
            [
                {
                    "代码": "sz300308",
                    "名称": "高成交额样本",
                    "最新价": 120.0,
                    "涨跌幅": 8.0,
                    "成交量": 1_000_000_000,
                    "成交额": 40_000_000_000,
                },
                {
                    "代码": "sz301566",
                    "名称": "高涨幅样本",
                    "最新价": 20.0,
                    "涨跌幅": 20.0,
                    "成交量": 120_000_000,
                    "成交额": 1_200_000_000,
                },
            ]
        )


class LowRiskMixedCapSpotAkshare(SinaDailyFallbackAkshare):
    def stock_zh_a_spot_em(self):
        raise RuntimeError("eastmoney spot disconnected")

    def stock_zh_a_spot(self):
        return FakeFrame(
            [
                {
                    "代码": "sz300308",
                    "名称": "超大市值样本",
                    "最新价": 120.0,
                    "涨跌幅": 8.0,
                    "成交量": 1_000_000_000,
                    "成交额": 40_000_000_000,
                },
                {
                    "代码": "sz300001",
                    "名称": "示例科技",
                    "最新价": 18.32,
                    "涨跌幅": 5.2,
                    "成交量": 320_000_000,
                    "成交额": 5_800_000_000,
                },
            ]
        )

    def stock_zh_a_daily(self, symbol, start_date, end_date, adjust):
        frame = super().stock_zh_a_daily(symbol, start_date, end_date, adjust)
        records = frame.to_dict("records")
        outstanding_share = 2_000_000_000 if symbol == "sz300308" else 1_000_000_000
        for row in records:
            row["outstanding_share"] = outstanding_share
        self.sina_daily_symbol = symbol
        return FakeFrame(records)


class ScienceBoardSpotAkshare(FakeAkshare):
    def stock_zh_a_spot_em(self):
        return FakeFrame(
            [
                {
                    "代码": "688757",
                    "名称": "科创样本",
                    "最新价": 18.32,
                    "涨跌幅": 20.0,
                    "成交量": 3_200_000,
                    "量比": 5.0,
                    "换手率": 8.0,
                    "流通市值": 8_800_000_000,
                },
                {
                    "代码": "300001",
                    "名称": "示例科技",
                    "最新价": 18.32,
                    "涨跌幅": 5.2,
                    "成交量": 3_200_000,
                    "量比": 2.5,
                    "换手率": 6.8,
                    "流通市值": 8_800_000_000,
                },
            ]
        )


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


class AkShareProviderTest(unittest.TestCase):
    def test_provider_builds_candidates_from_realtime_daily_and_minute_data(self):
        fake_ak = FakeAkshare()
        provider = AkShareProvider(ak_module=fake_ak, today=date(2026, 6, 3))

        candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=5)

        self.assertEqual(len(candidates), 2)
        candidate = candidates[0]
        self.assertEqual(candidate.code, "300001")
        self.assertEqual(candidate.name, "示例科技")
        self.assertEqual(candidate.board, "创业板")
        self.assertAlmostEqual(candidate.same_time_volumes_5d[0], 1_280_000)
        self.assertAlmostEqual(candidate.float_market_cap_billion, 88.0)
        self.assertGreater(candidate.ma5, candidate.ma10)
        self.assertEqual(candidate.recent_daily_volumes, [4_350_000, 4_400_000, 4_450_000])
        self.assertAlmostEqual(candidate.intraday_above_avg_ratio, 2 / 3)
        self.assertEqual(fake_ak.hist_calls[0], "300001")
        self.assertEqual(fake_ak.minute_calls[0], "300001")

    def test_provider_raises_clear_error_when_akshare_is_missing(self):
        with self.assertRaisesRegex(RuntimeError, "pip install akshare"):
            AkShareProvider(ak_module=None, import_module=lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)))

    def test_provider_can_prefer_akshare_sina_spot_before_eastmoney_when_requested(self):
        def fake_get(*args, **kwargs):
            raise AssertionError("eastmoney should not be called before low-risk sina spot")

        ak = AkshareSinaSpotFallbackAkshare()
        provider = AkShareProvider(
            ak_module=ak,
            today=date(2026, 6, 3),
            requests_get=fake_get,
            prefer_low_risk_spot=True,
        )

        candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

        self.assertEqual(candidates[0].code, "300001")
        self.assertEqual(ak.sina_daily_symbol, "sz300001")

    def test_provider_prioritizes_main_market_when_low_risk_spot_lacks_liquidity_fields(self):
        def fake_get(*args, **kwargs):
            raise AssertionError("network fallback should not be needed")

        ak = LowRiskMixedBoardSpotAkshare()
        provider = AkShareProvider(
            ak_module=ak,
            today=date(2026, 6, 3),
            requests_get=fake_get,
            prefer_low_risk_spot=True,
        )

        candidates = provider.fetch_candidates(max_candidates=1, enrich_limit=1)

        self.assertEqual(candidates[0].code, "300001")
        self.assertEqual(candidates[0].board, "创业板")

    def test_provider_prioritizes_pct_change_when_low_risk_spot_lacks_liquidity_fields(self):
        provider = AkShareProvider(
            ak_module=LowRiskMissingLiquidityRankAkshare(),
            today=date(2026, 6, 3),
            prefer_low_risk_spot=True,
        )

        candidates = provider.fetch_candidates(max_candidates=1, enrich_limit=1)

        self.assertEqual(candidates[0].code, "301566")

    def test_provider_continues_after_enriched_market_cap_is_out_of_range(self):
        provider = AkShareProvider(
            ak_module=LowRiskMixedCapSpotAkshare(),
            today=date(2026, 6, 3),
            prefer_low_risk_spot=True,
        )

        candidates = provider.fetch_candidates(max_candidates=2, enrich_limit=1)

        self.assertEqual(candidates[0].code, "300001")
        self.assertLessEqual(candidates[0].float_market_cap_billion, 400.0)

    def test_provider_excludes_science_board_candidates(self):
        provider = AkShareProvider(ak_module=ScienceBoardSpotAkshare(), today=date(2026, 6, 3))

        candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

        self.assertEqual(candidates[0].code, "300001")
        self.assertEqual(candidates[0].board, "创业板")

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

    def test_provider_falls_back_to_eastmoney_realtime_api_when_akshare_spot_fails(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": {
                        "diff": [
                            {
                                "f2": 18.32,
                                "f3": 5.2,
                                "f5": 3_200_000,
                                "f8": 6.8,
                                "f10": 2.5,
                                "f12": "300001",
                                "f14": "示例科技",
                                "f21": 8_800_000_000,
                            }
                        ]
                    }
                }

        def fake_get(url, params, headers, timeout):
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            captured["timeout"] = timeout
            return FakeResponse()

        provider = AkShareProvider(
            ak_module=FailingSpotAkshare(),
            today=date(2026, 6, 3),
            requests_get=fake_get,
        )

        candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

        self.assertEqual(candidates[0].code, "300001")
        self.assertIn("push2.eastmoney.com", captured["url"])
        self.assertIn("Mozilla", captured["headers"]["User-Agent"])
        self.assertEqual(captured["params"]["pz"], "100")
        self.assertEqual(captured["timeout"], 15)

    def test_provider_reports_clear_error_when_realtime_sources_fail(self):
        def failing_get(*args, **kwargs):
            raise RuntimeError("connection closed")

        provider = AkShareProvider(
            ak_module=FailingSpotAkshare(),
            today=date(2026, 6, 3),
            requests_get=failing_get,
        )

        with self.assertRaisesRegex(RuntimeError, "failed to fetch realtime A-share market data"):
            provider.fetch_candidates(max_candidates=10, enrich_limit=1)

    def test_provider_uses_sina_realtime_fallback_with_turnover_and_float_cap(self):
        calls = []

        class FakeResponse:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

            def json(self):
                raise ValueError("not eastmoney json")

        def fake_get(url, params, headers=None, timeout=10):
            calls.append((url, params))
            if "push2.eastmoney.com" in url:
                raise RuntimeError("eastmoney disconnected")
            return FakeResponse(
                '[{"symbol":"sz300001","code":"300001","name":"示例科技","trade":"18.32",'
                '"changepercent":5.2,"volume":320000000,"nmc":880000,"turnoverratio":6.8}]'
            )

        provider = AkShareProvider(
            ak_module=FailingSpotAkshare(),
            today=date(2026, 6, 3),
            requests_get=fake_get,
        )

        candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

        self.assertEqual(candidates[0].code, "300001")
        self.assertEqual(candidates[0].current_volume, 3_200_000)
        self.assertEqual(candidates[0].turnover_rate, 6.8)
        self.assertEqual(candidates[0].float_market_cap_billion, 88.0)
        self.assertTrue(any("vip.stock.finance.sina.com.cn" in call[0] for call in calls))

    def test_provider_uses_akshare_sina_spot_fallback_and_derives_missing_turnover_and_cap(self):
        def fake_get(*args, **kwargs):
            raise RuntimeError("remote source blocked")

        ak = AkshareSinaSpotFallbackAkshare()
        provider = AkShareProvider(
            ak_module=ak,
            today=date(2026, 6, 3),
            requests_get=fake_get,
        )

        candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].code, "300001")
        self.assertEqual(candidates[0].current_volume, 3_200_000)
        self.assertAlmostEqual(candidates[0].turnover_rate, 32.0)
        self.assertAlmostEqual(candidates[0].float_market_cap_billion, 183.2)
        self.assertEqual(ak.sina_daily_symbol, "sz300001")

    def test_provider_skips_candidate_when_daily_enrichment_fails(self):
        provider = AkShareProvider(ak_module=PartiallyFailingDailyAkshare(), today=date(2026, 6, 3))

        candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].code, "300002")

    def test_provider_uses_sina_daily_fallback_when_eastmoney_daily_fails(self):
        ak = SinaDailyFallbackAkshare()
        provider = AkShareProvider(ak_module=ak, today=date(2026, 6, 3))

        candidates = provider.fetch_candidates(max_candidates=10, enrich_limit=1)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(ak.sina_daily_symbol, "sz300001")
        self.assertEqual(candidates[0].recent_daily_volumes, [4_350_000, 4_400_000, 4_450_000])


if __name__ == "__main__":
    unittest.main()
