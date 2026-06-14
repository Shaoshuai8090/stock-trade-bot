"""A-share stock signal scanning toolkit."""

from trade_signal_tool.models import EvaluationResult, Signal, StockCandidate
from trade_signal_tool.after_close_strategy import AfterCloseConfig, AfterCloseStrategy
from trade_signal_tool.strategy import SignalStrategy, StrategyConfig

__all__ = [
    "AfterCloseConfig",
    "AfterCloseStrategy",
    "EvaluationResult",
    "Signal",
    "SignalStrategy",
    "StockCandidate",
    "StrategyConfig",
]
