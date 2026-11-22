"""FLY paper-account mark history.

Observations are recorded on startup and after simulated order execution only.
They are NOT historical market prices, validated performance, or daily NAV.
"""
from datetime import datetime, timezone

def observe(db, reason):
    cash = int(db.execute("SELECT cash FROM account WHERE id=1").fetchone()[0])
    invested = int(db.execute("SELECT COALESCE(SUM(qty * last_cents),0) FROM positions").fetchone()[0])
    equity = cash + invested
    if cash < 0 or invested < 0 or equity <= 0:
        raise ValueError("Invalid simulated account totals")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    db.execute(
        "INSERT INTO portfolio_marks(created_utc,reason,cash_cents,invested_cents,equity_cents) "
        "VALUES(?,?,?,?,?)", (timestamp,reason,cash,invested,equity)
    )

def ensure_table(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS portfolio_marks("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "created_utc TEXT NOT NULL,"
        "reason TEXT NOT NULL CHECK(reason IN ('START','PAPER_ORDER')),"
        "cash_cents INTEGER NOT NULL CHECK(cash_cents >= 0),"
        "invested_cents INTEGER NOT NULL CHECK(invested_cents >= 0),"
        "equity_cents INTEGER NOT NULL CHECK(equity_cents > 0))"
    )
    if db.execute("SELECT COUNT(*) FROM portfolio_marks").fetchone()[0] == 0:
        # Existing paper portfolios start from their *currently observed*
        # valuations; no historical performance is fabricated.
        observe(db, "START")

def history(db, limit=120):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("History limit out of range")
    rows = db.execute(
        "SELECT id,created_utc,reason,cash_cents,invested_cents,equity_cents "
        "FROM (SELECT * FROM portfolio_marks ORDER BY id DESC LIMIT ?) "
        "ORDER BY id ASC", (limit,)
    ).fetchall()
    points = [dict(r) for r in rows]
    if not points:
        raise ValueError("Missing paper portfolio baseline")
    first = points[0]["equity_cents"]
    last = points[-1]["equity_cents"]
    return {
        "mode":"PAPER MARK EVENTS ONLY",
        "valuation":"LAST USER-ENTERED HYPOTHETICAL MARKS",
        "return_calculation":"Unadjusted change between sampled portfolio equity observations; not a time-weighted or money-weighted return",
        "baseline_id": points[0]["id"],
        "observations":len(points),
        "equity_change_cents":last-first,
        "equity_change_pct":round((last-first)*100/first,2),
        "points":points,
        "disclaimer":"Marks recorded at startup and on simulated orders, not continuous prices; do not interpret as verified investment performance."
    }
