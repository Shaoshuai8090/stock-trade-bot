import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from trade_signal_tool.data import load_candidates_csv
from trade_signal_tool.models import StockCandidate


class DataAndCliTest(unittest.TestCase):
    def test_load_candidates_csv_parses_lists_and_booleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "code",
                        "name",
                        "board",
                        "price",
                        "pct_change",
                        "index_pct_change",
                        "current_volume",
                        "same_time_volumes_5d",
                        "turnover_rate",
                        "float_market_cap_billion",
                        "recent_daily_volumes",
                        "projected_daily_volume",
                        "ma5",
                        "ma10",
                        "ma20",
                        "ma60",
                        "ma60_prev",
                        "intraday_above_avg_ratio",
                        "recovered_after_avg_break",
                        "theme",
                        "theme_rank",
                        "has_hot_theme",
                        "pressure_distance_pct",
                        "upper_shadow_recent",
                        "is_st",
                        "is_suspended",
                        "listing_days",
                        "limit_up_seal_strength",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "code": "300001",
                        "name": "示例科技",
                        "board": "创业板",
                        "price": "18.32",
                        "pct_change": "5.2",
                        "index_pct_change": "1.1",
                        "current_volume": "3200000",
                        "same_time_volumes_5d": "1200000|1350000|1280000|1310000|1260000",
                        "turnover_rate": "6.8",
                        "float_market_cap_billion": "88",
                        "recent_daily_volumes": "8000000|9300000|10800000",
                        "projected_daily_volume": "13500000",
                        "ma5": "17.2",
                        "ma10": "16.5",
                        "ma20": "15.7",
                        "ma60": "14.9",
                        "ma60_prev": "14.6",
                        "intraday_above_avg_ratio": "0.86",
                        "recovered_after_avg_break": "true",
                        "theme": "机器人",
                        "theme_rank": "3",
                        "has_hot_theme": "true",
                        "pressure_distance_pct": "12",
                        "upper_shadow_recent": "false",
                        "is_st": "false",
                        "is_suspended": "false",
                        "listing_days": "360",
                        "limit_up_seal_strength": "0.62",
                    }
                )

            candidates = load_candidates_csv(path)

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].same_time_volumes_5d, [1200000, 1350000, 1280000, 1310000, 1260000])
            self.assertTrue(candidates[0].has_hot_theme)

    def test_cli_scan_outputs_json_signals(self):
        completed = subprocess.run(
            [sys.executable, "-m", "trade_signal_tool.cli", "scan", "--demo", "--json"],
            check=True,
            text=True,
            capture_output=True,
        )

        payload = json.loads(completed.stdout)

        self.assertGreaterEqual(len(payload["signals"]), 1)
        self.assertEqual(payload["signals"][0]["level"], "strong")
        self.assertIn("score", payload["signals"][0])

    def test_cli_scan_can_use_astock_provider(self):
        from trade_signal_tool.cli import main

        candidate = StockCandidate(
            code="300001",
            name="示例科技",
            board="创业板",
            price=18.32,
            pct_change=5.2,
            index_pct_change=1.1,
            current_volume=3_200_000,
            same_time_volumes_5d=[1_200_000, 1_350_000, 1_280_000, 1_310_000, 1_260_000],
            turnover_rate=6.8,
            float_market_cap_billion=88.0,
            recent_daily_volumes=[8_000_000, 9_300_000, 10_800_000],
            projected_daily_volume=13_500_000,
            ma5=17.2,
            ma10=16.5,
            ma20=15.7,
            ma60=14.9,
            ma60_prev=14.6,
            intraday_above_avg_ratio=0.86,
            recovered_after_avg_break=True,
            theme="机器人",
            theme_rank=3,
            has_hot_theme=True,
            pressure_distance_pct=12.0,
            upper_shadow_recent=False,
            is_st=False,
            is_suspended=False,
            listing_days=360,
            limit_up_seal_strength=0.62,
            data_source="tencent",
        )

        with patch("trade_signal_tool.cli.AStockDataProvider") as provider_class:
            provider_class.return_value.fetch_candidates.return_value = [candidate]
            with redirect_stdout(io.StringIO()):
                exit_code = main(["scan", "--provider", "astock", "--json", "--max-candidates", "50", "--enrich-limit", "3"])

        self.assertEqual(exit_code, 0)
        provider_class.return_value.fetch_candidates.assert_called_once_with(max_candidates=50, enrich_limit=3)

    def test_cli_scan_can_use_akshare_provider(self):
        from trade_signal_tool.cli import main

        candidate = StockCandidate(
            code="300001",
            name="示例科技",
            board="创业板",
            price=18.32,
            pct_change=5.2,
            index_pct_change=1.1,
            current_volume=3_200_000,
            same_time_volumes_5d=[1_200_000, 1_350_000, 1_280_000, 1_310_000, 1_260_000],
            turnover_rate=6.8,
            float_market_cap_billion=88.0,
            recent_daily_volumes=[8_000_000, 9_300_000, 10_800_000],
            projected_daily_volume=13_500_000,
            ma5=17.2,
            ma10=16.5,
            ma20=15.7,
            ma60=14.9,
            ma60_prev=14.6,
            intraday_above_avg_ratio=0.86,
            recovered_after_avg_break=True,
            theme="机器人",
            theme_rank=3,
            has_hot_theme=True,
            pressure_distance_pct=12.0,
            upper_shadow_recent=False,
            is_st=False,
            is_suspended=False,
            listing_days=360,
            limit_up_seal_strength=0.62,
        )

        with patch("trade_signal_tool.cli.AkShareProvider") as provider_class:
            provider_class.return_value.fetch_candidates.return_value = [candidate]
            with redirect_stdout(io.StringIO()):
                exit_code = main(["scan", "--provider", "akshare", "--json", "--max-candidates", "50", "--enrich-limit", "3"])

        self.assertEqual(exit_code, 0)
        provider_class.return_value.fetch_candidates.assert_called_once_with(max_candidates=50, enrich_limit=3)

    def test_cli_scan_reports_provider_error_without_traceback(self):
        from trade_signal_tool.cli import main

        with patch("trade_signal_tool.cli.AkShareProvider") as provider_class:
            provider_class.return_value.fetch_candidates.side_effect = RuntimeError("failed to fetch realtime A-share market data")
            stderr = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                exit_code = main(["scan", "--provider", "akshare", "--json"])

        self.assertEqual(exit_code, 1)
        self.assertIn("failed to fetch realtime A-share market data", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
