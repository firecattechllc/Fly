"""Read-only Alpaca US stock quotes with Keychain-backed credentials.

This module contains no brokerage order-submission capability.
"""
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_VALID = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
_ALLOWED_FEEDS = {"iex", "delayed_sip"}
_BASE = "https://data.alpaca.markets/v2/stocks/quotes/latest"
_KEYCHAIN_SERVICE = "com.firecattechnology.Sigil.dev.credentials"
_KEYCHAIN_ACCOUNTS = ("alpaca_api_key", "alpaca_secret_key")
_KEYCHAIN_PATH = Path.home() / "Library" / "Keychains" / "login.keychain-db"

class MarketDataError(Exception):
    pass

def _keychain_value(account):
    """Fetch one secret just-in-time. Never log, persist, or return it to callers."""
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", _KEYCHAIN_SERVICE,
             "-a", account, "-w", str(_KEYCHAIN_PATH)],
            check=True, capture_output=True, text=True, timeout=5,
        )
        value = result.stdout.rstrip("\r\n")
        if not value:
            raise MarketDataError("Alpaca credentials are unavailable in Keychain")
        return value
    except (OSError, subprocess.SubprocessError):
        raise MarketDataError("Alpaca credentials are unavailable in Keychain") from None

def _credentials():
    # Explicit process environment is supported for controlled test/deployment use.
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if key and secret:
        return key, secret
    if key or secret:
        raise MarketDataError("Both Alpaca credential components are required")
    return tuple(_keychain_value(account) for account in _KEYCHAIN_ACCOUNTS)

def configured():
    # Metadata-only check; never fetch secret values during dashboard refresh.
    if os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"):
        return True
    try:
        return all(subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", _KEYCHAIN_SERVICE,
             "-a", account, str(_KEYCHAIN_PATH)],
            check=True, capture_output=True, timeout=3,
        ).returncode == 0 for account in _KEYCHAIN_ACCOUNTS)
    except (OSError, subprocess.SubprocessError):
        return False

def get_quotes(symbols, feed="iex", opener=None, credential_loader=_credentials):
    """Receive up to 10 symbols; return provenance-tagged bid/ask data only."""
    if feed not in _ALLOWED_FEEDS:
        raise MarketDataError("Only IEX and delayed SIP feeds are supported")
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 10:
        raise MarketDataError("Provide 1-10 symbols")
    normalized = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not _VALID.fullmatch(symbol):
            raise MarketDataError("Invalid symbol")
        normalized.append(symbol)
    key, secret = credential_loader()
    url = _BASE + "?" + urllib.parse.urlencode({"symbols": ",".join(sorted(set(normalized))), "feed": feed})
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
        "User-Agent": "FLY/0.4 (read-only market-data)",
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
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        raise MarketDataError("Market-data request failed") from None
