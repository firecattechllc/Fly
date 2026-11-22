"""Read-only Alpaca historical daily bars and transparent research metrics.

The provider feed is not a consolidated market view; IEX may differ from SIP.
Research results are deterministic, not AI inference or investment advice.
"""
import json
import math
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

from market_data import MarketDataError, _VALID, _credentials

_BASE = "https://data.alpaca.markets/v2/stocks/"
_MAX_BODY = 262144
_ALLOWED_FEEDS = ("iex", "delayed_sip")


def _finite(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise MarketDataError("Unexpected historical data")
    num = float(value)
    if not math.isfinite(num) or (positive and num <= 0):
        raise MarketDataError("Unexpected historical data")
    return num


def _decode_bars(raw, symbol, feed, days):
    try:
        payload = json.loads(raw)
        bars = payload.get("bars")
        if not isinstance(bars, list):
            raise MarketDataError("Unexpected historical data")
        out = []
        previous = ""
        for bar in bars:
            if not isinstance(bar, dict):
                raise MarketDataError("Unexpected historical data")
            t = bar.get("t")
            if not isinstance(t, str) or not t or t <= previous:
                raise MarketDataError("Historical bars must be time ordered")
            previous = t
            o, h, l, c = (_finite(bar.get(k), positive=True) for k in ("o", "h", "l", "c"))
            if h < max(o, c, l) or l > min(o, c, h):
                raise MarketDataError("Invalid OHLC price bounds")
            v = bar.get("v")
            if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
                raise MarketDataError("Unexpected historical volume")
            out.append({"timestamp":t, "open":o, "high":h,
                        "low":l, "close":c, "volume":int(v)})
        if len(out) > 400:
            raise MarketDataError("Historical data exceeds configured limit")
        return {"provider":"alpaca", "symbol":symbol, "feed":feed, "days_requested":days,
                "timeframe":"1Day", "read_only":True, "broker_connected":False,
                "bars":out, "coverage":"IEX is single-exchange data; incomplete versus consolidated SIP."}
    except (ValueError, TypeError, OverflowError) as exc:
        raise MarketDataError("Malformed historical data") from None


def get_bars(symbol, days=90, feed="iex", opener=None, credential_loader=_credentials, now=None):
    if not isinstance(symbol, str) or not _VALID.fullmatch(symbol):
        raise MarketDataError("Invalid historical-data symbol")
    if type(days) is not int or not 5 <= days <= 365:
        raise MarketDataError("Historical lookback must be 5-365 days")
    if feed not in _ALLOWED_FEEDS:
        raise MarketDataError("Unsupported historical feed")
    key, secret = credential_loader()
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        raise MarketDataError("Historical cutoff must be timezone aware")
    # A delay avoids requesting a premium-only real-time SIP period.
    end = end.astimezone(timezone.utc) - timedelta(minutes=20)
    start = end - timedelta(days=days)
    params = urllib.parse.urlencode({
        "timeframe":"1Day", "start":start.isoformat().replace("+00:00","Z"),
        "end":end.isoformat().replace("+00:00","Z"),
        "feed":feed, "adjustment":"raw", "limit":"400", "sort":"asc"
    })
    url = _BASE + urllib.parse.quote(symbol, safe="") + "/bars?" + params
    req = urllib.request.Request(url,headers={
        "APCA-API-KEY-ID":key, "APCA-API-SECRET-KEY":secret,
        "Accept":"application/json", "User-Agent":"FLY/0.5 (read-only historical data)"
    },method="GET")
    try:
        if opener is None:
            response = urllib.request.urlopen(req, timeout=8, context=ssl.create_default_context())
        else:
            response = opener(req, timeout=8)
        with response as resp:
            if resp.status != 200:
                raise MarketDataError("Historical data unavailable")
            raw = resp.read(_MAX_BODY + 1)
        if len(raw) > _MAX_BODY:
            raise MarketDataError("Historical response too large")
        return _decode_bars(raw, symbol, feed, days)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise MarketDataError("Historical provider request failed") from None


def research(result):
    """Compute reproducible descriptive metrics; never predict future returns."""
    bars = result["bars"]
    close = [b["close"] for b in bars]
    if len(close) < 2:
        return {"symbol":result["symbol"],"feed":result["feed"],
                "observations":len(close),"status":"INSUFFICIENT_DATA",
                "message":"At least two daily bars are required",
                "not_ai":True,"not_investment_advice":True}
    returns = [close[i]/close[i-1]-1 for i in range(1,len(close))]
    delta = (close[-1]/close[0]-1)*100
    sma20 = mean(close[-20:]) if len(close) >= 20 else None
    sma50 = mean(close[-50:]) if len(close) >= 50 else None
    vol = stdev(returns) * math.sqrt(252) * 100 if len(returns)>=2 else None
    last = close[-1]
    return {"symbol":result["symbol"],"feed":result["feed"],
            "observations":len(close),"status":"DESCRIPTIVE_ONLY",
            "first_bar":bars[0]["timestamp"],"last_bar":bars[-1]["timestamp"],
            "latest_close":round(last,4), "observed_change_pct":round(delta,2),
            "sma20":round(sma20,4) if sma20 is not None else None,
            "sma50":round(sma50,4) if sma50 is not None else None,
            "sample_annualized_volatility_pct":round(vol,2) if vol is not None else None,
            "trend_vs_sma20":("ABOVE" if last>sma20 else "BELOW_OR_EQUAL") if sma20 is not None else "INSUFFICIENT_DATA",
            "analysis":"Descriptive historical statistics only. No price forecast, buy/sell signal, factor model, or AI model.",
            "adjustment":"raw / unadjusted; splits and dividends can distort observed changes",
            "not_ai":True, "not_investment_advice":True}
