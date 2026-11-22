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
from historical import get_bars as alpaca_bars, research as historical_research
from market_cache import MARKET_CACHE
from analytics import calculate as calculate_analytics
from portfolio_intelligence import report as intelligence_report
from performance import ensure_table as ensure_marks, observe as record_mark, history as mark_history
from simulation import ensure_baseline, replay as replay_simulation
from market_simulation import calculate as calculate_market_simulation
from pdf_report import render as render_pdf_report
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
    db.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, created_utc TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL CHECK(side IN ('BUY','SELL')), qty INTEGER NOT NULL CHECK(qty > 0), price_cents INTEGER NOT NULL CHECK(price_cents > 0), notional_cents INTEGER NOT NULL CHECK(notional_cents > 0))")
    db.execute("INSERT OR IGNORE INTO account(id,cash) VALUES (1,?)", (STARTING_CASH,))
    ensure_marks(db)
    ensure_baseline(db)
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
            from datetime import datetime, timezone
            db.execute("INSERT INTO transactions(created_utc,symbol,side,qty,price_cents,notional_cents) VALUES(?,?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(),symbol,side,qty,price,amount))
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
        elif path == "/api/simulation":
            with LOCK:
                db=connection()
                try:
                    self.respond(200,replay_simulation(db))
                finally:
                    db.close()
        elif path == "/api/simulation/market":
            try:
                with LOCK:
                    db=connection()
                    try:
                        baseline=db.execute("SELECT created_utc,positions_json FROM simulation_baseline WHERE id=1").fetchone()
                        if baseline is None:
                            self.respond(409,{"status":"BASELINE_REQUIRED"}); return
                        import json as _json
                        symbols={p["symbol"] for p in _json.loads(baseline["positions_json"])}
                        symbols.update(r[0] for r in db.execute("SELECT DISTINCT symbol FROM transactions"))
                        if not symbols:
                            self.respond(200,{"status":"INSUFFICIENT_DATA","points":[],"message":"No holdings or transactions exist yet."}); return
                        symbols.add("SPY")
                        factor_symbols={"QQQ","IWM","IWD","MTUM","USMV"}
                        if len(symbols)>11:
                            self.respond(400,{"error":"Market simulation supports at most 10 portfolio symbols plus SPY"}); return
                        histories={}
                        for symbol in sorted(symbols):
                            histories[symbol]=MARKET_CACHE.get(("bars",symbol,365,"iex"),300,
                                lambda symbol=symbol:alpaca_bars(symbol,365,"iex"))
                        for symbol in sorted(factor_symbols):
                            try:
                                histories[symbol]=MARKET_CACHE.get(("bars",symbol,365,"iex"),300,
                                    lambda symbol=symbol:alpaca_bars(symbol,365,"iex"))
                            except MarketDataError:
                                pass  # Optional factor coverage must not block reconciled portfolio/benchmark reporting.
                        result=calculate_market_simulation(db,histories)
                        self.respond(200,result)
                    finally:
                        db.close()
            except MarketDataError as exc:
                self.respond(503,{"status":"MARKET_DATA_UNAVAILABLE","error":str(exc),"read_only":True})
        elif path == "/api/report.pdf":
            try:
                with LOCK:
                    db=connection()
                    try:
                        baseline=db.execute("SELECT positions_json FROM simulation_baseline WHERE id=1").fetchone()
                        if baseline is None:
                            self.respond(409,{"error":"Opening baseline unavailable"}); return
                        import json as _json
                        symbols={p["symbol"] for p in _json.loads(baseline["positions_json"])}
                        symbols.update(r[0] for r in db.execute("SELECT DISTINCT symbol FROM transactions"))
                        if not symbols:
                            self.respond(409,{"error":"No portfolio activity exists for a performance report"}); return
                        symbols.add("SPY")
                        if len(symbols)>11:
                            self.respond(400,{"error":"Report supports at most 10 portfolio symbols plus SPY"}); return
                        histories={s:MARKET_CACHE.get(("bars",s,365,"iex"),300,
                            lambda s=s:alpaca_bars(s,365,"iex")) for s in sorted(symbols)}
                        for s in sorted({"QQQ","IWM","IWD","MTUM","USMV"}):
                            try:
                                histories[s]=MARKET_CACHE.get(("bars",s,365,"iex"),300,
                                    lambda s=s:alpaca_bars(s,365,"iex"))
                            except MarketDataError:
                                pass  # Factor proxies are supplemental and may be unavailable.
                        report=calculate_market_simulation(db,histories)
                    finally:
                        db.close()
                if report.get("status")!="DAILY_MARKET_REPLAY":
                    self.respond(409,{"error":"A reconciled market simulation is required before PDF export","detail":report}); return
                report["generated_utc"]=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                raw=render_pdf_report(report)
                self.send_response(200); self.send_header("Content-Type","application/pdf")
                self.send_header("Content-Disposition","attachment; filename=fly-performance-report.pdf")
                self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store")
                self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(raw)
            except MarketDataError as exc:
                self.respond(503,{"error":"Market data unavailable","detail":str(exc)})
        elif path == "/api/intelligence":
            with LOCK:
                db = connection()
                try:
                    self.respond(200, intelligence_report(db, snapshot(db)))
                finally:
                    db.close()
        elif path == "/api/report.csv":
            with LOCK:
                db = connection()
                try:
                    state=snapshot(db); report=intelligence_report(db,state)
                    rows=["section,metric,value"]
                    rows.append("portfolio,cash_cents,"+str(state["cash_cents"]))
                    rows.append("portfolio,equity_cents,"+str(state["equity_cents"]))
                    for x in report["sector_exposure"]["sectors"]:
                        rows.append("sector,"+x["sector"]+","+str(x["weight_pct"]))
                    for x in report["stress_testing"]["scenarios"]:
                        rows.append("stress,"+x["id"]+","+str(x["hypothetical_pnl_cents"]))
                    raw=("\\n".join(rows)+"\\n").encode()
                    self.send_response(200); self.send_header("Content-Type","text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", "attachment; filename=fly-paper-report.csv")
                    self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw)
                finally:
                    db.close()
        elif path == "/api/state":
            with LOCK:
                db = connection()
                try:
                    self.respond(200, snapshot(db))
                finally:
                    db.close()
        elif path == "/api/analytics":
            query = parse_qs(urlparse(self.path).query)
            try:
                days = int(query.get("days", ["90"])[0])
                if type(days) is not int or not 30 <= days <= 365:
                    raise ValueError("Analytics lookback must be 30-365 days")
                with LOCK:
                    db = connection()
                    try:
                        positions = snapshot(db)["positions"]
                    finally:
                        db.close()
                if len(positions) > 10:
                    raise ValueError("Analytics currently supports at most 10 holdings")
                symbols = sorted({p["symbol"] for p in positions} | {"SPY"})
                histories = {}
                for symbol in symbols:
                    histories[symbol] = MARKET_CACHE.get(
                        ("bars", symbol, days, "iex"), 300,
                        lambda symbol=symbol: alpaca_bars(symbol, days, "iex"))
                self.respond(200, calculate_analytics(positions, histories))
            except (ValueError, MarketDataError) as exc:
                self.respond(503 if isinstance(exc, MarketDataError) else 400,
                             {"error": str(exc) if isinstance(exc, MarketDataError) else "Invalid analytics request", "read_only": True})
        elif path in ("/api/historical", "/api/research"):
            query = parse_qs(urlparse(self.path).query)
            symbol = query.get("symbol", ["SPY"])[0].upper()
            try:
                days = int(query.get("days", ["90"])[0])
                feed = query.get("feed", ["iex"])[0]
                bars = MARKET_CACHE.get(("bars", symbol, days, feed), 300,
                                        lambda: alpaca_bars(symbol, days, feed))
                self.respond(200, bars if path == "/api/historical" else historical_research(bars))
            except (ValueError, MarketDataError) as exc:
                self.respond(503 if isinstance(exc, MarketDataError) else 400,
                             {"error": str(exc) if isinstance(exc, MarketDataError) else "Invalid lookback", "read_only": True})
        elif path == "/api/quotes":
            query = parse_qs(urlparse(self.path).query)
            symbols = query.get("symbols", [""])[0].upper().split(",")
            feed = query.get("feed", ["iex"])[0]
            try:
                self.respond(200, MARKET_CACHE.get(
                    ("quotes", tuple(sorted(symbols)), feed), 15,
                    lambda: get_quotes(symbols, feed)))
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
