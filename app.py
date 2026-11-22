"""FLY: deliberately paper-only, local portfolio intelligence workspace."""
import json
import os
import re
import secrets
import sqlite3
import threading
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from market_data import MarketDataError, configured as alpaca_configured, get_quotes
from risk import calculate as calculate_risk
from performance import ensure_table as ensure_marks, observe as record_mark, history as mark_history
import auth

os.umask(0o077)  # Restrict SQLite and log files to the hosting user
DB = Path(os.environ.get("FLY_DB", str(Path(__file__).parent / "data" / "paper.db")))
PUBLIC = Path(__file__).parent / "static" / "index.html"
LOCK = threading.RLock()
STARTING_CASH = 10000000  # cents; simulated $100k
MAX_ORDER_BPS = 1000  # 10% of equity
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")


def connection():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), cash INTEGER NOT NULL CHECK(cash >= 0))")
    db.execute("CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, qty INTEGER NOT NULL CHECK(qty >= 0), last_cents INTEGER NOT NULL CHECK(last_cents > 0))")
    db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, kind TEXT NOT NULL, payload TEXT NOT NULL)")
    db.execute("INSERT OR IGNORE INTO account(id,cash) VALUES (1,?)", (STARTING_CASH,))
    ensure_marks(db)
    db.commit()
    return db


def parse_positive_cents(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Price must be a positive decimal number")
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d <= 0 or d > Decimal("1000000"):
            raise ValueError("Price out of range")
        if d.as_tuple().exponent < -2:
            raise ValueError("Maximum two decimal places")
        cents = int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return cents
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid price")


def snapshot(db):
    cash = int(db.execute("SELECT cash FROM account WHERE id=1").fetchone()[0])
    positions = [dict(r) for r in db.execute("SELECT symbol, qty, last_cents FROM positions ORDER BY symbol")]
    equity = cash + sum(p["qty"] * p["last_cents"] for p in positions)
    events = [dict(r) for r in db.execute("SELECT id, created, kind, payload FROM events ORDER BY id DESC LIMIT 30")]
    for e in events:
        e["payload"] = json.loads(e["payload"])
    return {"mode": "SIMULATION ONLY", "feed": "MANUAL HYPOTHETICAL PRICES",
            "cash_cents": cash, "equity_cents": equity, "positions": positions,
            "events": events, "max_order_percent_equity": 10, "broker_connected": False, "market_data_configured": alpaca_configured()}


def trade(payload):
    if not isinstance(payload, dict):
        raise ValueError("Request must be a JSON object")
    symbol = str(payload.get("symbol", "")).upper().strip()
    side = payload.get("side")
    qty = payload.get("qty")
    if not SYMBOL.fullmatch(symbol):
        raise ValueError("Symbol must contain 1-10 uppercase letters, numbers or dots")
    if side not in ("BUY", "SELL"):
        raise ValueError("Side must be BUY or SELL")
    if type(qty) is not int or not 1 <= qty <= 100000:
        raise ValueError("Quantity must be a whole number from 1 to 100000")
    price = parse_positive_cents(payload.get("price"))
    with LOCK:
        db = connection()
        try:
            db.execute("BEGIN IMMEDIATE")
            before = snapshot(db)
            amount = qty * price
            old = db.execute("SELECT qty FROM positions WHERE symbol=?", (symbol,)).fetchone()
            held = int(old[0]) if old else 0
            if side == "BUY":
                if amount > before["cash_cents"]:
                    raise ValueError("Insufficient simulated cash")
                if amount * 10000 > before["equity_cents"] * MAX_ORDER_BPS:
                    raise ValueError("Order exceeds 10% of simulated equity")
                db.execute("UPDATE account SET cash=cash-? WHERE id=1", (amount,))
                db.execute("INSERT INTO positions(symbol,qty,last_cents) VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET qty=qty+excluded.qty,last_cents=excluded.last_cents", (symbol, qty, price))
            else:
                if qty > held:
                    raise ValueError("Insufficient simulated shares")
                db.execute("UPDATE account SET cash=cash+? WHERE id=1", (amount,))
                remaining = held - qty
                if remaining:
                    db.execute("UPDATE positions SET qty=?,last_cents=? WHERE symbol=?", (remaining, price, symbol))
                else:
                    db.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
            event = {"symbol": symbol, "side": side, "qty": qty, "hypothetical_price_cents": price, "notional_cents": amount}
            db.execute("INSERT INTO events(kind,payload) VALUES(?,?)", ("PAPER_ORDER", json.dumps(event, sort_keys=True)))
            record_mark(db, "PAPER_ORDER")
            db.commit()
            return snapshot(db)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        raw = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def auth_response(self, status, payload, cookie=None):
        raw = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def serve_public_asset(self, name, mime, csp=None):
        raw = (PUBLIC.parent / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if csp:
            self.send_header("Content-Security-Policy", csp)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get("Host", "").split(":")[0].lower() not in ("127.0.0.1", "localhost"):
            return self.respond(403, {"error":"Localhost access only"})
        path = urlparse(self.path).path
        if path == "/style.css":
            return self.serve_public_asset("style.css", "text/css; charset=utf-8")
        if path == "/auth.js":
            return self.serve_public_asset("auth.js", "text/javascript; charset=utf-8")
        if path == "/auth":
            return self.serve_public_asset("auth.html", "text/html; charset=utf-8",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'")
        session = auth.session_for(self.headers)
        if path == "/api/auth/status":
            return self.respond(200, {"configured": auth.is_configured(), "authenticated": bool(session)})
        if path == "/healthz":
            try:
                with connection() as db:
                    check = db.execute("PRAGMA quick_check").fetchone()[0]
                if check != "ok":
                    return self.respond(503, {"status": "unhealthy", "mode": "paper"})
                return self.respond(200, {"status": "ok", "mode": "paper", "database": "ok"})
            except sqlite3.Error:
                return self.respond(503, {"status": "unhealthy", "mode": "paper", "database": "unavailable"})
        if not session:
            if path == "/":
                self.send_response(302)
                self.send_header("Location", "/auth")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            return self.respond(401, {"error": "Owner authentication required"})
        if path == "/":
            html = PUBLIC.read_text(encoding="utf-8").replace("__TOKEN__", session["csrf"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(html)
        elif path == "/app.js":
            js = (PUBLIC.parent / "app.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(js)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.end_headers()
            self.wfile.write(js)
        elif path == "/style.css":
            css = (PUBLIC.parent / "style.css").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(css)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.end_headers()
            self.wfile.write(css)
        elif path == "/api/performance":
            with LOCK:
                db = connection()
                try:
                    self.respond(200, mark_history(db))
                finally:
                    db.close()
        elif path == "/api/risk":
            with LOCK:
                db = connection()
                try:
                    self.respond(200, calculate_risk(snapshot(db)))
                finally:
                    db.close()
        elif path == "/api/state":
            with LOCK:
                db = connection()
                try:
                    self.respond(200, snapshot(db))
                finally:
                    db.close()
        elif path == "/api/quotes":
            query = parse_qs(urlparse(self.path).query)
            symbols = query.get("symbols", [""])[0].upper().split(",")
            feed = query.get("feed", ["iex"])[0]
            try:
                self.respond(200, get_quotes(symbols, feed))
            except MarketDataError as exc:
                self.respond(503, {"error": str(exc), "read_only": True})
        elif path == "/healthz":
            try:
                with connection() as db:
                    check = db.execute("PRAGMA quick_check").fetchone()[0]
                if check != "ok":
                    return self.respond(503, {"status": "unhealthy", "mode": "paper"})
                self.respond(200, {"status": "ok", "mode": "paper", "database": "ok"})
            except sqlite3.Error:
                self.respond(503, {"status": "unhealthy", "mode": "paper", "database": "unavailable"})
        else:
            self.respond(404, {"error": "Not found"})

    def do_POST(self):
        if self.headers.get("Host", "").split(":")[0].lower() not in ("127.0.0.1", "localhost"):
            return self.respond(403, {"error":"Localhost access only"})
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin != "http://" + host:
            return self.respond(403, {"error": "Invalid Origin"})
        path = urlparse(self.path).path
        if path in ("/api/auth/setup", "/api/auth/login", "/api/auth/logout"):
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self.respond(415, {"error":"Expected application/json"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 1 <= n <= 4096:
                    return self.respond(413, {"error":"Invalid request size"})
                payload = json.loads(self.rfile.read(n))
                if not isinstance(payload, dict):
                    raise ValueError("Expected JSON object")
            except (ValueError, json.JSONDecodeError):
                return self.respond(400, {"error":"Invalid JSON request"})
            if path == "/api/auth/setup":
                try:
                    sid = auth.create_owner(payload.get("password"))
                    return self.auth_response(200, {"authenticated": True},
                                              auth.cookie_header(sid))
                except ValueError as exc:
                    return self.respond(400, {"error":str(exc)})
            if path == "/api/auth/login":
                ip = self.client_address[0]
                if not auth.allowed_login(ip):
                    return self.respond(429, {"error":"Too many attempts. Try later."})
                if not auth.verify_password(payload.get("password")):
                    auth.record_failed_login(ip)
                    return self.respond(401, {"error":"Invalid owner credentials"})
                auth.reset_failed_login(ip)
                sid = auth.make_session()
                return self.auth_response(200, {"authenticated":True}, auth.cookie_header(sid))
            session = auth.session_for(self.headers)
            if not session or self.headers.get("X-Fly-Token") != session["csrf"]:
                return self.respond(403, {"error":"Invalid session or CSRF token"})
            auth.end_session(self.headers)
            return self.auth_response(200, {"authenticated":False}, auth.expire_cookie_header())
        if path != "/api/paper-orders":
            return self.respond(404, {"error": "Not found"})
        session = auth.session_for(self.headers)
        if not session:
            return self.respond(401, {"error":"Owner authentication required"})
        if self.headers.get("X-Fly-Token") != session["csrf"]:
            return self.respond(403, {"error": "Invalid CSRF token"})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.respond(415, {"error": "Expected application/json"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 1 <= n <= 4096:
                return self.respond(413, {"error": "Invalid request size"})
            payload = json.loads(self.rfile.read(n))
            self.respond(200, trade(payload))
        except (ValueError, json.JSONDecodeError) as e:
            self.respond(400, {"error": str(e)})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    with connection() as db:
        print("FLY initialized; MODE=SIMULATED, no broker adapter", flush=True)
    ThreadingHTTPServer((os.environ.get("FLY_HOST", "127.0.0.1"), 8877), Handler).serve_forever()
