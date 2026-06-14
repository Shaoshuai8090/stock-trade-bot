import os
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from trade_signal_tool.config import Settings, load_dotenv
from trade_signal_tool.models import Signal
from trade_signal_tool.notifier import TelegramNotifier, notifier_from_options


class ConfigAndTelegramTest(unittest.TestCase):
    def test_settings_loads_telegram_config_from_spot_trade_bot_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "TELEGRAM_BOT_TOKEN=spot-token",
                        "TELEGRAM_CHAT_ID=spot-chat",
                    ]
                ),
                encoding="utf-8",
            )
            old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            old_chat = os.environ.pop("TELEGRAM_CHAT_ID", None)
            try:
                settings = Settings.from_env(spot_env_path=env_path)
            finally:
                if old_token is not None:
                    os.environ["TELEGRAM_BOT_TOKEN"] = old_token
                if old_chat is not None:
                    os.environ["TELEGRAM_CHAT_ID"] = old_chat

        self.assertEqual(settings.telegram_bot_token, "spot-token")
        self.assertEqual(settings.telegram_chat_id, "spot-chat")

    def test_load_dotenv_does_not_override_existing_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("TELEGRAM_CHAT_ID=from-file\n", encoding="utf-8")
            old_value = os.environ.get("TELEGRAM_CHAT_ID")
            os.environ["TELEGRAM_CHAT_ID"] = "from-env"
            try:
                load_dotenv(env_path)
                self.assertEqual(os.environ["TELEGRAM_CHAT_ID"], "from-env")
            finally:
                if old_value is None:
                    os.environ.pop("TELEGRAM_CHAT_ID", None)
                else:
                    os.environ["TELEGRAM_CHAT_ID"] = old_value

    def test_telegram_message_contains_a_share_signal_fields_and_disclaimer(self):
        signal = Signal(
            code="300001",
            name="示例科技",
            level="strong",
            score=96.51,
            signal_type="题材共振型",
            reasons=["量比放大", "均线多头发散"],
            metrics={
                "volume_ratio": 2.5,
                "turnover_rate": 6.8,
                "float_market_cap_billion": 88.0,
                "intraday_relative_strength": 4.1,
                "intraday_above_avg_ratio": 0.86,
            },
            theme="机器人",
            data_source="tencent",
        )

        message = TelegramNotifier.format_signal_message(signal)

        self.assertIn("A股交易信号提醒", message)
        self.assertIn("股票: 300001 示例科技", message)
        self.assertIn("信号等级: strong", message)
        self.assertIn("题材: 机器人", message)
        self.assertIn("量比: 2.50", message)
        self.assertIn("数据源: tencent", message)
        self.assertIn("仅为信号提醒，不构成投资建议。", message)

    def test_telegram_notifier_posts_send_message_request(self):
        signal = Signal(
            code="300001",
            name="示例科技",
            level="strong",
            score=96.51,
            signal_type="题材共振型",
            reasons=["量比放大"],
            metrics={"volume_ratio": 2.5, "turnover_rate": 6.8, "float_market_cap_billion": 88.0},
            theme="机器人",
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok": true}'

        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["data"] = request.data.decode("utf-8")
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("trade_signal_tool.notifier.urllib.request.urlopen", fake_urlopen):
            TelegramNotifier("token", "chat", timeout_seconds=3, retry_delay_seconds=0).send([signal])

        self.assertEqual(captured["url"], "https://api.telegram.org/bottoken/sendMessage")
        self.assertIn("chat_id=chat", captured["data"])
        self.assertIn("disable_web_page_preview=true", captured["data"])
        self.assertEqual(captured["timeout"], 3)

    def test_telegram_notifier_sends_after_close_heartbeat_when_no_signals(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok": true}'

        captured = {}

        def fake_urlopen(request, timeout):
            captured["data"] = request.data.decode("utf-8")
            return FakeResponse()

        with patch("trade_signal_tool.notifier.urllib.request.urlopen", fake_urlopen):
            TelegramNotifier("token", "chat").send_after_close_summary([])

        payload = urllib.parse.parse_qs(captured["data"])

        self.assertIn("A股收盘筛选完成", payload["text"][0])
        self.assertIn("今日无符合策略的股票", payload["text"][0])

    def test_telegram_notifier_retries_transient_send_failures(self):
        signal = Signal(
            code="300001",
            name="示例科技",
            level="watch",
            score=76.0,
            signal_type="观察型",
            reasons=["短线修复"],
            metrics={"volume_ratio": 1.2, "turnover_rate": 5.1, "float_market_cap_billion": 90.0},
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok": true}'

        attempts = {"count": 0}

        def flaky_urlopen(request, timeout):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise TimeoutError("timed out")
            return FakeResponse()

        with patch("trade_signal_tool.notifier.urllib.request.urlopen", flaky_urlopen):
            TelegramNotifier("token", "chat", timeout_seconds=3, retry_delay_seconds=0).send([signal])

        self.assertEqual(attempts["count"], 2)

    def test_notifier_factory_uses_telegram_settings_when_requested(self):
        settings = Settings(telegram_bot_token="token", telegram_chat_id="chat")

        notifier = notifier_from_options(webhook_url=None, telegram=True, settings=settings)

        self.assertIsInstance(notifier, TelegramNotifier)


if __name__ == "__main__":
    unittest.main()
