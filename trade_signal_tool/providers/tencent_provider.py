import re
import urllib.parse
import urllib.request
from dataclasses import replace
from typing import Any, Callable, Dict, Iterable, List, Optional

from trade_signal_tool.models import StockCandidate


class TencentRealtimeProvider:
    def __init__(
        self,
        urlopen: Optional[Callable[..., Any]] = None,
        timeout_seconds: float = 10.0,
        batch_size: int = 60,
    ):
        self.urlopen = urlopen or urllib.request.urlopen
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size

    def fetch_records(self, codes: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        symbols = [_tencent_symbol(code) for code in codes]
        records: Dict[str, Dict[str, Any]] = {}
        for index in range(0, len(symbols), self.batch_size):
            batch = symbols[index : index + self.batch_size]
            if not batch:
                continue
            url = "https://qt.gtimg.cn/q=" + urllib.parse.quote(",".join(batch), safe=",")
            response = self.urlopen(url, timeout=self.timeout_seconds)
            text = response.read().decode("gbk", "ignore")
            records.update(self._parse_response(text))
        return records

    def refresh_candidates(self, candidates: Iterable[StockCandidate]) -> List[StockCandidate]:
        candidates = list(candidates)
        records = self.fetch_records(candidate.code for candidate in candidates)
        refreshed = []
        for candidate in candidates:
            record = records.get(candidate.code)
            if not record:
                refreshed.append(candidate)
                continue
            refreshed.append(
                replace(
                    candidate,
                    name=record["name"] or candidate.name,
                    price=record["price"] or candidate.price,
                    pct_change=record["pct_change"],
                    current_volume=record["current_volume"] or candidate.current_volume,
                    turnover_rate=record["turnover_rate"] or candidate.turnover_rate,
                    float_market_cap_billion=record["float_market_cap_billion"] or candidate.float_market_cap_billion,
                    projected_daily_volume=max(record["current_volume"] or 0, candidate.projected_daily_volume),
                    data_source="tencent",
                )
            )
        return refreshed

    def _parse_response(self, text: str) -> Dict[str, Dict[str, Any]]:
        records = {}
        for _, payload in re.findall(r'v_([a-z]{2}\d{6})="([^"]*)"', text):
            fields = payload.split("~")
            if len(fields) < 46:
                continue
            code = fields[2].zfill(6)
            price = _num(fields, 3)
            pct_change = _num(fields, 32)
            current_volume = int(_num(fields, 36))
            turnover_rate = _num(fields, 38)
            float_cap = _num(fields, 45) or _num(fields, 44)
            records[code] = {
                "code": code,
                "name": fields[1],
                "price": price,
                "pct_change": pct_change,
                "current_volume": current_volume,
                "turnover_rate": turnover_rate,
                "float_market_cap_billion": float_cap,
            }
        return records


def _tencent_symbol(code: str) -> str:
    code = "".join(ch for ch in str(code) if ch.isdigit())[-6:].zfill(6)
    if code.startswith(("6", "688", "689")):
        return "sh" + code
    return "sz" + code


def _num(fields: List[str], index: int) -> float:
    if index >= len(fields):
        return 0.0
    value = fields[index].strip()
    if not value or value == "--":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0
