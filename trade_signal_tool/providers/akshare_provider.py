import importlib
import json
import math
from dataclasses import replace
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, Callable, Dict, Iterable, List, Optional

from trade_signal_tool.models import StockCandidate
from trade_signal_tool.providers.concept_theme_provider import ConceptThemeProvider


class AkShareProvider:
    def __init__(
        self,
        ak_module: Optional[Any] = None,
        today: Optional[date] = None,
        import_module: Callable[[str], Any] = importlib.import_module,
        requests_get: Optional[Callable[..., Any]] = None,
        prefer_low_risk_spot: bool = False,
        enable_concept_theme: bool = True,
        hot_concept_limit: int = 20,
        max_rough_pct_change: Optional[float] = None,
    ):
        if ak_module is None:
            try:
                ak_module = import_module("akshare")
            except ModuleNotFoundError as exc:
                raise RuntimeError("AkShare is required for real market data. Install it with: pip install akshare") from exc
        self.ak = ak_module
        self.today = today or date.today()
        self.requests_get = requests_get
        self.prefer_low_risk_spot = prefer_low_risk_spot
        self.enable_concept_theme = enable_concept_theme
        self.concept_theme_provider = ConceptThemeProvider(ak_module, hot_concept_limit=hot_concept_limit)
        self.max_rough_pct_change = max_rough_pct_change

    def fetch_candidates(self, max_candidates: int = 80, enrich_limit: int = 20) -> List[StockCandidate]:
        spot_records = self._spot_records()
        rough = [record for record in spot_records if self._passes_rough_filters(record)]
        rough.sort(key=self._rough_rank_key, reverse=True)
        candidates = []
        for record in rough[: max_candidates]:
            candidate = self._enrich_record(record)
            if candidate is not None and self._passes_enriched_rough_filters(candidate):
                candidates.append(candidate)
            if len(candidates) >= enrich_limit:
                break
        return self._with_concept_themes(candidates)

    def _with_concept_themes(self, candidates: List[StockCandidate]) -> List[StockCandidate]:
        if not self.enable_concept_theme or not candidates:
            return candidates
        try:
            assignments = self.concept_theme_provider.assignments_for_codes(candidate.code for candidate in candidates)
        except Exception:
            return candidates
        if not assignments:
            return candidates
        return [
            replace(
                candidate,
                theme=assignments[candidate.code].theme,
                theme_rank=assignments[candidate.code].theme_rank,
                has_hot_theme=True,
            )
            if candidate.code in assignments
            else candidate
            for candidate in candidates
        ]

    def trading_days(self) -> List[str]:
        frame = self.ak.tool_trade_date_hist_sina()
        records = _records(frame)
        days = []
        for row in records:
            value = row.get("trade_date") or row.get("交易日") or row.get("date")
            if value is None:
                continue
            days.append(str(value).replace("-", ""))
        return days

    def _spot_records(self) -> List[Dict[str, Any]]:
        try:
            return _records(self.ak.stock_zh_a_spot_em())
        except Exception as akshare_error:
            fallback_methods = (
                [self._akshare_sina_spot_records, self._sina_spot_records, self._eastmoney_spot_records]
                if self.prefer_low_risk_spot
                else [self._eastmoney_spot_records, self._sina_spot_records, self._akshare_sina_spot_records]
            )
            last_error = akshare_error
            for method in fallback_methods:
                try:
                    return method()
                except Exception as exc:
                    last_error = exc
            raise RuntimeError("failed to fetch realtime A-share market data from AkShare/Eastmoney/Sina") from last_error

    def _eastmoney_spot_records(self) -> List[Dict[str, Any]]:
        requests_get = self.requests_get
        if requests_get is None:
            requests_get = importlib.import_module("requests").get
        params = {
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f12",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": "f2,f3,f5,f6,f8,f10,f12,f14,f21",
        }
        last_error = None
        diff = []
        for url in [
            "https://82.push2.eastmoney.com/api/qt/clist/get",
            "https://push2.eastmoney.com/api/qt/clist/get",
            "https://80.push2.eastmoney.com/api/qt/clist/get",
        ]:
            try:
                response = requests_get(
                    url,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15,
                )
                response.raise_for_status()
                diff = response.json().get("data", {}).get("diff", [])
                break
            except Exception as exc:
                last_error = exc
        if not diff and last_error is not None:
            raise last_error
        return [
            {
                "最新价": item.get("f2"),
                "涨跌幅": item.get("f3"),
                "成交量": item.get("f5"),
                "成交额": item.get("f6"),
                "换手率": item.get("f8"),
                "量比": item.get("f10"),
                "代码": item.get("f12"),
                "名称": item.get("f14"),
                "流通市值": item.get("f21"),
            }
            for item in diff
        ]

    def _sina_spot_records(self) -> List[Dict[str, Any]]:
        requests_get = self.requests_get
        if requests_get is None:
            requests_get = importlib.import_module("requests").get
        records = []
        page = 1
        while page <= 80:
            response = requests_get(
                "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
                params={
                    "page": str(page),
                    "num": "80",
                    "sort": "turnoverratio",
                    "asc": "0",
                    "node": "hs_a",
                    "symbol": "",
                    "_s_r_a": "page",
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            response.raise_for_status()
            page_records = json.loads(response.text)
            if not page_records:
                break
            records.extend(page_records)
            if len(page_records) < 80:
                break
            page += 1
        return [
            {
                "最新价": item.get("trade"),
                "涨跌幅": item.get("changepercent"),
                "成交量": _num(item, "volume") / 100,
                "成交额": item.get("amount"),
                "换手率": item.get("turnoverratio"),
                "量比": 0,
                "代码": item.get("code"),
                "名称": item.get("name"),
                "流通市值": _num(item, "nmc") * 10_000,
            }
            for item in records
        ]

    def _akshare_sina_spot_records(self) -> List[Dict[str, Any]]:
        return [
            {
                "最新价": item.get("最新价"),
                "涨跌幅": item.get("涨跌幅"),
                "成交量": _num(item, "成交量") / 100,
                "_成交量_股": _num(item, "成交量"),
                "成交额": item.get("成交额", 0),
                "换手率": item.get("换手率", 0),
                "量比": item.get("量比", 0),
                "代码": _clean_code(item.get("代码", "")),
                "名称": item.get("名称"),
                "流通市值": item.get("流通市值", 0),
            }
            for item in _records(self.ak.stock_zh_a_spot())
        ]

    def _passes_rough_filters(self, record: Dict[str, Any]) -> bool:
        name = str(record.get("名称", ""))
        code = _clean_code(record.get("代码", ""))
        price = _num(record, "最新价")
        if not name or "ST" in name.upper() or price <= 0:
            return False
        if _is_science_board_code(code):
            return False
        volume_ratio = _num(record, "量比")
        turnover_rate = _num(record, "换手率")
        float_cap_billion = _num(record, "流通市值") / 100_000_000
        pct_change = _num(record, "涨跌幅")
        liquidity_fields_missing = volume_ratio == 0 and turnover_rate == 0 and float_cap_billion == 0
        if liquidity_fields_missing and _is_beijing_code(code):
            return False
        if self.max_rough_pct_change is not None and pct_change > self.max_rough_pct_change:
            return False
        return (
            (volume_ratio >= 0.8 or volume_ratio == 0)
            and (turnover_rate == 0 or 3 <= turnover_rate <= 18)
            and (float_cap_billion == 0 or 50 <= float_cap_billion <= 400)
            and pct_change > 0
        )

    def _rough_rank_key(self, record: Dict[str, Any]) -> tuple:
        code = _clean_code(record.get("代码", ""))
        volume_ratio = _num(record, "量比")
        turnover_rate = _num(record, "换手率")
        float_cap_billion = _num(record, "流通市值") / 100_000_000
        has_liquidity_fields = 1 if volume_ratio > 0 or turnover_rate > 0 or float_cap_billion > 0 else 0
        main_market = 0 if _is_beijing_code(code) else 1
        if not has_liquidity_fields:
            return (
                0,
                main_market,
                _num(record, "涨跌幅"),
                _num(record, "成交额"),
                _num(record, "成交量"),
                0.0,
                0.0,
            )
        return (
            1,
            volume_ratio,
            turnover_rate,
            main_market,
            _num(record, "成交额"),
            _num(record, "涨跌幅"),
            _num(record, "成交量"),
        )

    def _passes_enriched_rough_filters(self, candidate: StockCandidate) -> bool:
        return 50 <= candidate.float_market_cap_billion <= 400

    def _enrich_record(self, record: Dict[str, Any]) -> Optional[StockCandidate]:
        code = _clean_code(record.get("代码", ""))
        try:
            daily_records = self._daily_records(code)
        except Exception:
            return None
        if len(daily_records) < 60:
            return None

        closes = [_num(row, "收盘") for row in daily_records if _num(row, "收盘") > 0]
        highs = [_num(row, "最高") for row in daily_records if _num(row, "最高") > 0]
        volumes = [int(_num(row, "成交量")) for row in daily_records if _num(row, "成交量") > 0]
        if len(closes) < 60 or len(volumes) < 3:
            return None

        price = _num(record, "最新价")
        current_volume = int(_num(record, "成交量"))
        volume_ratio = _num(record, "量比")
        turnover_rate = _num(record, "换手率")
        float_market_cap_billion = _num(record, "流通市值") / 100_000_000
        outstanding_share = _latest_outstanding_share(daily_records)
        if turnover_rate <= 0 and outstanding_share > 0:
            current_volume_shares = _num(record, "_成交量_股") or current_volume * 100
            turnover_rate = current_volume_shares / outstanding_share * 100
        if float_market_cap_billion <= 0 and outstanding_share > 0 and price > 0:
            float_market_cap_billion = price * outstanding_share / 100_000_000
        avg_same_time = current_volume / volume_ratio if volume_ratio > 0 else mean(volumes[-5:])
        minute_ratio = self._intraday_above_average_ratio(code)
        pressure_distance = self._pressure_distance_pct(price, highs[-60:])

        return StockCandidate(
            code=code,
            name=str(record.get("名称", "")),
            board=_board_for_code(code),
            price=price,
            pct_change=_num(record, "涨跌幅"),
            index_pct_change=0.0,
            current_volume=current_volume,
            same_time_volumes_5d=[int(avg_same_time)] * 5,
            turnover_rate=turnover_rate,
            float_market_cap_billion=float_market_cap_billion,
            recent_daily_volumes=volumes[-3:],
            projected_daily_volume=max(current_volume, volumes[-1]),
            ma5=mean(closes[-5:]),
            ma10=mean(closes[-10:]),
            ma20=mean(closes[-20:]),
            ma60=mean(closes[-60:]),
            ma60_prev=mean(closes[-61:-1]) if len(closes) >= 61 else mean(closes[-60:]),
            intraday_above_avg_ratio=minute_ratio,
            recovered_after_avg_break=minute_ratio >= 0.7,
            theme="",
            theme_rank=None,
            has_hot_theme=False,
            pressure_distance_pct=pressure_distance,
            upper_shadow_recent=False,
            is_st=False,
            is_suspended=False,
            listing_days=len(daily_records),
            limit_up_seal_strength=None,
        )

    def _daily_records(self, code: str) -> List[Dict[str, Any]]:
        start = (self.today - timedelta(days=180)).strftime("%Y%m%d")
        end = self.today.strftime("%Y%m%d")
        try:
            frame = self.ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
            return _records(frame)
        except Exception:
            return self._sina_daily_records(code, start, end)

    def _sina_daily_records(self, code: str, start: str, end: str) -> List[Dict[str, Any]]:
        frame = self.ak.stock_zh_a_daily(symbol=_sina_symbol_for_code(code), start_date=start, end_date=end, adjust="")
        return [
            {
                "日期": row.get("date"),
                "股票代码": code,
                "开盘": row.get("open"),
                "收盘": row.get("close"),
                "最高": row.get("high"),
                "最低": row.get("low"),
                "成交量": _num(row, "volume") / 100,
                "成交额": row.get("amount"),
                "换手率": _num(row, "turnover") * 100,
                "流通股本": row.get("outstanding_share"),
            }
            for row in _records(frame)
        ]

    def _intraday_above_average_ratio(self, code: str) -> float:
        start = datetime.combine(self.today, datetime.min.time()).replace(hour=9, minute=30).strftime("%Y-%m-%d %H:%M:%S")
        end = datetime.combine(self.today, datetime.min.time()).replace(hour=15, minute=0).strftime("%Y-%m-%d %H:%M:%S")
        try:
            frame = self.ak.stock_zh_a_hist_min_em(symbol=code, start_date=start, end_date=end, period="1", adjust="")
        except Exception:
            return 1.0
        records = _records(frame)
        comparable = []
        for row in records:
            close = _num(row, "收盘")
            avg_price = _num(row, "均价")
            if close > 0 and avg_price > 0:
                comparable.append(close >= avg_price)
        if not comparable:
            return 1.0
        return sum(1 for item in comparable if item) / len(comparable)

    def _pressure_distance_pct(self, price: float, highs: Iterable[float]) -> float:
        if price <= 0:
            return 0.0
        overhead_highs = [high for high in highs if high > price]
        if not overhead_highs:
            return 999.0
        nearest = min(overhead_highs)
        return (nearest - price) / price * 100


def _records(frame: Any) -> List[Dict[str, Any]]:
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict("records"))
    return list(frame)


def _num(record: Dict[str, Any], key: str) -> float:
    value = record.get(key, 0)
    if value is None:
        return 0.0
    if isinstance(value, float) and math.isnan(value):
        return 0.0
    text = str(value).strip()
    if not text or text in {"-", "nan", "None"}:
        return 0.0
    return float(text)


def _clean_code(value: Any) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-6:].zfill(6)


def _latest_outstanding_share(daily_records: List[Dict[str, Any]]) -> float:
    for row in reversed(daily_records):
        value = _num(row, "流通股本")
        if value > 0:
            return value
    return 0.0


def _is_beijing_code(code: str) -> bool:
    return code.startswith(("8", "4", "9"))


def _is_science_board_code(code: str) -> bool:
    return code.startswith("68")


def _board_for_code(code: str) -> str:
    if code.startswith("300") or code.startswith("301"):
        return "创业板"
    if code.startswith("688") or code.startswith("689"):
        return "科创板"
    if _is_beijing_code(code):
        return "北交所"
    if code.startswith("6"):
        return "沪市主板"
    return "深市主板"


def _sina_symbol_for_code(code: str) -> str:
    if code.startswith(("6", "688", "689")):
        return f"sh{code}"
    if code.startswith(("8", "4", "9")):
        return f"bj{code}"
    return f"sz{code}"
