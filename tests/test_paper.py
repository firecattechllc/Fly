import os
import tempfile
import unittest
from pathlib import Path
import app

class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = app.DB
        app.DB = Path(self.tmp.name) / "paper.db"
    def tearDown(self):
        app.DB = self.old
        self.tmp.cleanup()
    def test_initial_portfolio(self):
        with app.connection() as db:
            state = app.snapshot(db)
            self.assertEqual(state["cash_cents"], 10000000)
            self.assertFalse(state["broker_connected"])
    def test_paper_round_trip(self):
        state = app.trade({"symbol":"AAPL","side":"BUY","qty":2,"price":"100.00"})
        self.assertEqual(state["cash_cents"], 9980000)
        self.assertEqual(state["positions"][0]["qty"], 2)
        state = app.trade({"symbol":"AAPL","side":"SELL","qty":2,"price":"101.00"})
        self.assertEqual(state["cash_cents"], 10000200)
        self.assertEqual(len(state["positions"]), 0)
        self.assertEqual(len(state["events"]), 2)
    def test_large_order_rejected(self):
        with self.assertRaisesRegex(ValueError,"10%"):
            app.trade({"symbol":"AAPL","side":"BUY","qty":20,"price":"1000"})
    def test_no_shorting(self):
        with self.assertRaisesRegex(ValueError,"Insufficient simulated shares"):
            app.trade({"symbol":"AAPL","side":"SELL","qty":1,"price":"50"})
    def test_reject_fractional_price_and_qty(self):
        for payload in ({"symbol":"AAPL","side":"BUY","qty":1,"price":"1.001"},
                        {"symbol":"AAPL","side":"BUY","qty":1.2,"price":"1.00"}):
            with self.assertRaises(ValueError):
                app.trade(payload)
    def test_rejected_order_not_persisted(self):
        with self.assertRaises(ValueError):
            app.trade({"symbol":"AAPL","side":"SELL","qty":1,"price":"10"})
        with app.connection() as db:
            self.assertEqual(app.snapshot(db)["events"], [])
if __name__ == "__main__":
    unittest.main()
