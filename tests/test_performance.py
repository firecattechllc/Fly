import sqlite3
import tempfile
import unittest
from pathlib import Path
import app
import performance

class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = app.DB
        app.DB = Path(self.tmp.name) / "paper.db"
        with app.connection() as db:
            self.assertEqual(performance.history(db)["observations"], 1)
    def tearDown(self):
        app.DB = self.previous
        self.tmp.cleanup()
    def test_start_baseline_is_not_duplicated(self):
        with app.connection() as db:
            record=performance.history(db)
            self.assertEqual(record["observations"], 1)
            self.assertEqual(record["points"][0]["reason"], "START")
            self.assertEqual(record["equity_change_cents"], 0)
    def test_orders_are_observed_atomically(self):
        before=app.trade({"symbol":"AAPL","side":"BUY","qty":1,"price":"100.00"})
        with app.connection() as db:
            points=performance.history(db)["points"]
            self.assertEqual(len(points), 2)
            self.assertEqual(points[-1]["reason"], "PAPER_ORDER")
            self.assertEqual(points[-1]["cash_cents"], before["cash_cents"])
            self.assertEqual(points[-1]["equity_cents"], before["equity_cents"])
            self.assertEqual(points[-1]["equity_cents"], 10000000)
    def test_rejected_order_does_not_mark_or_trade(self):
        with self.assertRaises(ValueError):
            app.trade({"symbol":"AAPL","side":"BUY","qty":100000,"price":"1000.00"})
        with app.connection() as db:
            self.assertEqual(performance.history(db)["observations"], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0],0)
    def test_existing_database_is_baselined_from_current_marks(self):
        with app.connection() as db:
            db.execute("DELETE FROM portfolio_marks")
            db.execute("UPDATE account SET cash=9000000 WHERE id=1")
            db.execute("INSERT INTO positions(symbol,qty,last_cents) VALUES('ABC',100,10000)")
            db.commit()
        with app.connection() as db:
            h=performance.history(db)
            self.assertEqual(h["observations"],1)
            self.assertEqual(h["points"][0]["equity_cents"],10000000)
            self.assertEqual(h["equity_change_cents"],0)

if __name__ == "__main__":
    unittest.main()
