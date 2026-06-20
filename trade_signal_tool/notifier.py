import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable, Optional

from trade_signal_tool.config import Settings
from trade_signal_tool.models import Signal


class ConsoleNotifier:
    def send(self, signals: Iterable[Signal]) -> None:
        for signal in signals:
            print(format_signal(signal))

    def send_after_close_summary(self, signals: Iterable[Signal]) -> None:
        signals = list(signals)
        if not signals:
            print("A股收盘筛选完成：今日无符合策略的股票。服务正常运行。")
            return
        self.send(signals)


class WebhookNotifier:
    def __init__(self, url: str, timeout_seconds: float = 5.0):
        self.url = url
        self.timeout_seconds = timeout_seconds

    def send(self, signals: Iterable[Signal]) -> None:
        payload = json.dumps({"signals": [signal.to_dict() for signal in signals]}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds):
            return

    def send_after_close_summary(self, signals: Iterable[Signal]) -> None:
        self.send(signals)


class TelegramNotifier:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        retry_delay_seconds: float = 2.0,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)

    @staticmethod
    def format_signal_message(signal: Signal) -> str:
        reasons = "\n".join(f"- {reason}" for reason in signal.reasons)
        theme = f"\n题材: {signal.theme}" if signal.theme else ""
        source = f"\n数据源: {signal.data_source}" if signal.data_source else ""
        metrics = signal.metrics
        trade_plan = TelegramNotifier._format_trade_plan(metrics)
        return (
            "A股收盘观察信号\n"
            f"股票: {signal.code} {signal.name}\n"
            f"信号等级: {signal.level}\n"
            f"信号类型: {signal.signal_type}\n"
            f"综合评分: {signal.score:.2f}\n"
            f"量比: {metrics.get('volume_ratio', 0):.2f}\n"
            f"换手率: {metrics.get('turnover_rate', 0):.2f}%\n"
            f"流通市值: {metrics.get('float_market_cap_billion', 0):.1f}亿\n"
            f"相对指数强度: {metrics.get('intraday_relative_strength', 0):.2f}%\n"
            f"分时均线上方占比: {metrics.get('intraday_above_avg_ratio', 0):.0%}\n"
            f"MA5乖离: {metrics.get('ma5_gap_pct', 0):.2f}% | MA10乖离: {metrics.get('ma10_gap_pct', 0):.2f}%"
            f"{theme}"
            f"{source}\n"
            f"交易计划:\n{trade_plan}\n"
            f"触发因子:\n{reasons}\n\n"
            "仅为信号提醒，不构成投资建议。请自行确认仓位和风险。"
        )

    @staticmethod
    def _format_trade_plan(metrics: dict) -> str:
        low = metrics.get("buy_zone_low", 0)
        high = metrics.get("buy_zone_high", 0)
        stop_loss = metrics.get("stop_loss", 0)
        return (
            "- 动作: 次日只等回踩或承接确认，不追高\n"
            f"- 参考买区: {low:.2f}-{high:.2f}\n"
            f"- 止损参考: {stop_loss:.2f}\n"
            "- 失效条件: 高开远离买区、跌破 MA20、量能异常放大但承接不足"
        )

    def send(self, signals: Iterable[Signal]) -> None:
        for signal in signals:
            self._send_text(self.format_signal_message(signal))

    def send_after_close_summary(self, signals: Iterable[Signal]) -> None:
        signals = list(signals)
        if not signals:
            self._send_text(
                "A股收盘筛选完成\n"
                "结果: 今日无符合策略的股票\n"
                "状态: 服务正常运行，行情扫描和策略过滤已完成\n\n"
                "仅为信号提醒，不构成投资建议。"
            )
            return
        self._send_text(f"A股收盘筛选完成\n结果: 筛出 {len(signals)} 只符合策略的股票")
        self.send(signals)

    def _send_text(self, text: str) -> None:
        if not self.bot_token or not self.chat_id:
            raise RuntimeError("telegram bot token and chat id are required")
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        request = urllib.request.Request(url, data=payload, method="POST")
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read().decode("utf-8")
                parsed = json.loads(body)
                if not parsed.get("ok"):
                    raise RuntimeError(f"telegram sendMessage failed: {body}")
                return
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                time.sleep(self.retry_delay_seconds)
        raise RuntimeError(f"telegram sendMessage failed after {self.max_attempts} attempts: {last_error}")


def format_signal(signal: Signal) -> str:
    metrics = signal.metrics
    lines = [
        f"{signal.code} {signal.name} [{signal.level}] {signal.score:.2f}分",
        f"类型：{signal.signal_type}",
        f"量比：{metrics.get('volume_ratio', 0):.2f} | 换手率：{metrics.get('turnover_rate', 0):.2f}% | 流通市值：{metrics.get('float_market_cap_billion', 0):.1f}亿",
        f"相对指数强度：{metrics.get('intraday_relative_strength', 0):.2f}% | 分时均线上方占比：{metrics.get('intraday_above_avg_ratio', 0):.0%}",
        f"参考买区：{metrics.get('buy_zone_low', 0):.2f}-{metrics.get('buy_zone_high', 0):.2f} | 止损参考：{metrics.get('stop_loss', 0):.2f}",
    ]
    if signal.theme:
        lines.append(f"题材：{signal.theme}")
    lines.append("触发原因：" + "；".join(signal.reasons))
    return "\n".join(lines)


def notifier_from_options(
    webhook_url: Optional[str],
    telegram: bool = False,
    settings: Optional[Settings] = None,
):
    if telegram:
        settings = settings or Settings.from_env()
        return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    if webhook_url:
        return WebhookNotifier(webhook_url)
    return ConsoleNotifier()
