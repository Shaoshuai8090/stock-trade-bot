from dataclasses import replace
from datetime import date
from typing import Any, Callable, Optional

from trade_signal_tool.providers.akshare_provider import AkShareProvider
from trade_signal_tool.providers.tencent_provider import TencentRealtimeProvider


class AStockDataProvider:
    """A-share provider with a-stock-data style source priority.

    The current system still uses AkShare/Sina/Eastmoney to enumerate the full
    market because Tencent is better as a known-symbol realtime endpoint. After
    the base candidate pool is built, Tencent refreshes realtime fields for the
    smaller candidate set.
    """

    def __init__(
        self,
        base_provider: Optional[Any] = None,
        realtime_provider: Optional[TencentRealtimeProvider] = None,
        today: Optional[date] = None,
        import_module: Optional[Callable[[str], Any]] = None,
        requests_get: Optional[Callable[..., Any]] = None,
    ):
        kwargs = {}
        if today is not None:
            kwargs["today"] = today
        if import_module is not None:
            kwargs["import_module"] = import_module
        if requests_get is not None:
            kwargs["requests_get"] = requests_get
        kwargs["prefer_low_risk_spot"] = True
        self.base_provider = base_provider or AkShareProvider(**kwargs)
        self.realtime_provider = realtime_provider or TencentRealtimeProvider()

    def fetch_candidates(self, max_candidates: int = 80, enrich_limit: int = 20):
        candidates = self.base_provider.fetch_candidates(max_candidates=max_candidates, enrich_limit=enrich_limit)
        base_candidates = [replace(candidate, data_source=candidate.data_source or "akshare") for candidate in candidates]
        if not base_candidates:
            return base_candidates
        try:
            return self.realtime_provider.refresh_candidates(base_candidates)
        except Exception:
            return base_candidates

    def trading_days(self):
        return self.base_provider.trading_days()
