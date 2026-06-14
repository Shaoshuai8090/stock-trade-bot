import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import patch

from trade_signal_tool.cli import main
from trade_signal_tool.models import StockCandidate
from trade_signal_tool.schedule import is_after_close_window, is_trading_day


def candidate():
    return StockCandidate(
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


class ClosePushTest(unittest.TestCase):
    def test_after_close_window_starts_at_1505_china_time(self):
        before = datetime(2026, 6, 4, 7, 4, tzinfo=timezone.utc)
        after = datetime(2026, 6, 4, 7, 6, tzinfo=timezone.utc)

        self.assertFalse(is_after_close_window(before, utc_offset_hours=8))
        self.assertTrue(is_after_close_window(after, utc_offset_hours=8))

    def test_trading_day_uses_provider_calendar_when_available(self):
        self.assertTrue(is_trading_day("20260604", ["20260603", "20260604"]))
        self.assertFalse(is_trading_day("20260606", ["20260603", "20260604"]))

    def test_close_push_sends_telegram_after_close_on_trading_day(self):
        with patch("trade_signal_tool.cli.is_trading_day", return_value=True), \
            patch("trade_signal_tool.cli.is_after_close_window", return_value=True), \
            patch("trade_signal_tool.cli.AStockDataProvider") as provider_class, \
            patch("trade_signal_tool.cli.AfterCloseStrategy") as strategy_class, \
            patch("trade_signal_tool.cli.notifier_from_options") as notifier_factory:
            provider_class.return_value.fetch_candidates.return_value = [candidate()]
            strategy_class.return_value.scan.return_value = []
            notifier = notifier_factory.return_value
            with redirect_stdout(io.StringIO()):
                exit_code = main(["close-push", "--telegram", "--force-calendar"])

        self.assertEqual(exit_code, 0)
        strategy_class.return_value.scan.assert_called_once()
        notifier.send_after_close_summary.assert_called_once()
        sent_signals = notifier.send_after_close_summary.call_args.args[0]
        self.assertEqual(sent_signals, [])

    def test_close_push_sends_summary_even_when_no_signals(self):
        with patch("trade_signal_tool.cli.is_trading_day", return_value=True), \
            patch("trade_signal_tool.cli.is_after_close_window", return_value=True), \
            patch("trade_signal_tool.cli.AStockDataProvider") as provider_class, \
            patch("trade_signal_tool.cli.notifier_from_options") as notifier_factory:
            provider_class.return_value.fetch_candidates.return_value = []
            notifier = notifier_factory.return_value
            with redirect_stdout(io.StringIO()):
                exit_code = main(["close-push", "--telegram", "--force-calendar"])

        self.assertEqual(exit_code, 0)
        notifier.send_after_close_summary.assert_called_once_with([])
        notifier.send.assert_not_called()

    def test_close_push_skips_before_close(self):
        with patch("trade_signal_tool.cli.is_trading_day", return_value=True), \
            patch("trade_signal_tool.cli.is_after_close_window", return_value=False), \
            patch("trade_signal_tool.cli.AStockDataProvider") as provider_class:
            with redirect_stdout(io.StringIO()):
                exit_code = main(["close-push", "--telegram", "--force-calendar"])

        self.assertEqual(exit_code, 0)
        provider_class.assert_not_called()


if __name__ == "__main__":
    unittest.main()
