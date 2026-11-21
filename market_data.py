"""Read-only Alpaca US stock quotes. Never imports a brokerage trading client."""
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

_VALID = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
_ALLOWED_FEEDS = {"iex", "delayed_sip"}
_BASE = "https://data.alpaca.markets/v2/stocks/quotes/latest"

class MarketDataError(Exception):
    pass

def configured():
    return bool(os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"))

def get_quotes(symbols, feed="iex", opener=None):
    """Receive up to 10 symbols; return provenance-tagged bid/ask data only."""
    if not configured():
        raise MarketDataError("Alpaca market-data credentials are not configured")
    if feed not in _ALLOWED_FEEDS:
        raise MarketDataError("Only IEX and delayed SIP feeds are supported")
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 10:
        raise MarketDataError("Provide 1-10 symbols")
    normalized = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not _VALID.fullmatch(symbol):
            raise MarketDataError("Invalid symbol")
        normalized.append(symbol)
    url = _BASE + "?" + urllib.parse.urlencode({"symbols": ",".join(sorted(set(normalized))), "feed": feed})
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
        "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"],
        "Accept": "application/json",
        "User-Agent": "OpenSIGIL/0.2 (read-only market-data)",
    }, method="GET")
    try:
        if opener is None:
            with urllib.request.urlopen(req, timeout=7, context=ssl.create_default_context()) as resp:
                if resp.status != 200:
                    raise MarketDataError("Market-data provider unavailable")
                raw = resp.read(65537)
        else:
            with opener(req, timeout=7) as resp:
                if resp.status != 200:
                    raise MarketDataError("Market-data provider unavailable")
                raw = resp.read(65537)
        if len(raw) > 65536:
            raise MarketDataError("Market-data response too large")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("quotes"), dict):
            raise MarketDataError("Unexpected market-data response")
        quotes = []
        for sym in normalized:
            q = payload["quotes"].get(sym)
            if not isinstance(q, dict):
                continue
            quotes.append({"symbol": sym, "bid": q.get("bp"), "ask": q.get("ap"), "timestamp": q.get("t")})
        return {"provider": "alpaca", "source": feed, "requested_at": datetime.now(timezone.utc).isoformat(),
                "quotes": quotes, "read_only": True, "broker_connected": False}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise MarketDataError("Market-data request failed") from None
