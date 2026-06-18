import argparse
import json
import sys
from pathlib import Path

from trade_signal_tool.config import Settings
from trade_signal_tool.data import load_candidates_csv, signals_to_dicts
from trade_signal_tool.demo import demo_candidates
from trade_signal_tool.after_close_strategy import AfterCloseConfig, AfterCloseStrategy
from trade_signal_tool.notifier import notifier_from_options
from trade_signal_tool.providers import AkShareProvider, AStockDataProvider
from trade_signal_tool.schedule import china_now, is_after_close_window, is_trading_day, weekday_trading_day_fallback
from trade_signal_tool.strategy import SignalStrategy, StrategyConfig


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="trade-signal-tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Scan candidates and emit trading signals")
    scan.add_argument("--input", type=Path, help="CSV file containing candidate snapshots")
    scan.add_argument("--demo", action="store_true", help="Use built-in demo candidates")
    scan.add_argument("--provider", choices=["akshare", "astock"], help="Fetch real market data from a provider")
    scan.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    scan.add_argument("--webhook-url", help="POST JSON signals to a webhook")
    scan.add_argument("--telegram", action="store_true", help="Push signals to Telegram using spot-trade-bot config")
    scan.add_argument(
        "--telegram-env",
        type=Path,
        help="Path to spot-trade-bot .env; defaults to the sibling spot-trade-bot project",
    )
    scan.add_argument("--watch-threshold", type=float, default=75.0)
    scan.add_argument("--strong-threshold", type=float, default=85.0)
    scan.add_argument("--limit", type=int, default=10)
    scan.add_argument("--max-candidates", type=int, default=80, help="Provider rough-scan limit before enrichment")
    scan.add_argument("--enrich-limit", type=int, default=20, help="Provider daily/minute enrichment limit")

    close_push = subparsers.add_parser("close-push", help="Run after-close A-share scan and push Telegram signals")
    close_push.add_argument("--telegram", action="store_true", help="Push signals to Telegram using spot-trade-bot config")
    close_push.add_argument("--telegram-env", type=Path, help="Path to spot-trade-bot .env")
    close_push.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    close_push.add_argument("--watch-threshold", type=float, default=75.0)
    close_push.add_argument("--strong-threshold", type=float, default=85.0)
    close_push.add_argument("--limit", type=int, default=10)
    close_push.add_argument("--max-candidates", type=int, default=200)
    close_push.add_argument("--enrich-limit", type=int, default=30)
    close_push.add_argument("--force", action="store_true", help="Run even before the after-close window")
    close_push.add_argument("--force-calendar", action="store_true", help="Skip external trading-calendar lookup")

    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            return _scan(args)
        if args.command == "close-push":
            return _close_push(args)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _scan(args) -> int:
    if args.demo:
        candidates = demo_candidates()
    elif args.input:
        candidates = load_candidates_csv(args.input)
    elif args.provider == "akshare":
        candidates = AkShareProvider().fetch_candidates(
            max_candidates=args.max_candidates,
            enrich_limit=args.enrich_limit,
        )
    elif args.provider == "astock":
        candidates = AStockDataProvider().fetch_candidates(
            max_candidates=args.max_candidates,
            enrich_limit=args.enrich_limit,
        )
    else:
        raise SystemExit("scan requires --demo, --input, or --provider akshare/astock")

    strategy = AfterCloseStrategy(
        AfterCloseConfig(
            watch_threshold=args.watch_threshold,
            strong_threshold=args.strong_threshold,
        )
    )
    signals = strategy.scan(candidates)[: args.limit]

    if args.json:
        print(json.dumps({"signals": signals_to_dicts(signals)}, ensure_ascii=False, indent=2))
    else:
        settings = Settings.from_env(args.telegram_env) if args.telegram else None
        notifier_from_options(args.webhook_url, telegram=args.telegram, settings=settings).send(signals)

    return 0


def _close_push(args) -> int:
    now = china_now()
    today = now.strftime("%Y%m%d")

    if not args.force and not is_after_close_window(now):
        print("skip: after-close window has not started")
        return 0

    if not args.force_calendar:
        provider = AStockDataProvider()
        try:
            trading_calendar = provider.trading_days()
            today_is_trading_day = is_trading_day(today, trading_calendar)
        except Exception:
            today_is_trading_day = weekday_trading_day_fallback(now)
    else:
        today_is_trading_day = True

    if not today_is_trading_day:
        print(f"skip: {today} is not an A-share trading day")
        return 0

    provider = locals().get("provider") or AStockDataProvider()
    candidates = provider.fetch_candidates(max_candidates=args.max_candidates, enrich_limit=args.enrich_limit)
    strategy = AfterCloseStrategy(
        AfterCloseConfig(
            watch_threshold=args.watch_threshold,
            strong_threshold=args.strong_threshold,
        )
    )
    signals = strategy.scan(candidates)[: args.limit]

    if args.json:
        print(json.dumps({"signals": signals_to_dicts(signals)}, ensure_ascii=False, indent=2))
    else:
        settings = Settings.from_env(args.telegram_env) if args.telegram else None
        notifier_from_options(None, telegram=args.telegram, settings=settings).send_after_close_summary(signals)
        print(f"pushed {len(signals)} after-close signals")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
