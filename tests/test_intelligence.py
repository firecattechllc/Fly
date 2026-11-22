import sqlite3
import unittest
from sectors import classify
from portfolio_intelligence import stress_test, attribution

class IntelligenceTests(unittest.TestCase):
 def test_known_sector_and_unknown_are_separated(self):
  r=classify([{"symbol":"AAPL","qty":2,"last_cents":10000},{"symbol":"XYZ","qty":1,"last_cents":5000}])
  self.assertEqual(r["status"],"PARTIAL")
  self.assertEqual(r["sectors"][0]["sector"],"Information Technology")
  self.assertEqual(r["unclassified"][0]["symbol"],"XYZ")
 def test_stress_scenarios_are_deterministic_and_negative(self):
  r=stress_test([{"symbol":"AAPL","qty":10,"last_cents":10000}],50000)
  self.assertEqual(len(r["scenarios"]),5)
  self.assertTrue(all(x["hypothetical_pnl_cents"]<0 for x in r["scenarios"]))
 def test_transaction_ledger_realized_and_unrealized(self):
  db=sqlite3.connect(":memory:");db.row_factory=sqlite3.Row
  db.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY,created_utc TEXT,symbol TEXT,side TEXT,qty INTEGER,price_cents INTEGER,notional_cents INTEGER)")
  db.execute("INSERT INTO transactions VALUES(1,'t','AAPL','BUY',10,1000,10000)")
  db.execute("INSERT INTO transactions VALUES(2,'t','AAPL','SELL',4,1200,4800)")
  result=attribution(db,[{"symbol":"AAPL","qty":6,"last_cents":1100}])
  self.assertEqual(result["realized_pnl_cents"],800)
  self.assertEqual(result["unrealized_pnl_cents"],600)
  self.assertEqual(result["total_pnl_cents"],1400)
 def test_attribution_refuses_unreconciled_preexisting_positions(self):
  db=sqlite3.connect(":memory:");db.row_factory=sqlite3.Row
  db.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY,created_utc TEXT,symbol TEXT,side TEXT,qty INTEGER,price_cents INTEGER,notional_cents INTEGER)")
  with self.assertRaises(ValueError):
   attribution(db,[{"symbol":"AAPL","qty":1,"last_cents":1000}])
if __name__=="__main__":unittest.main()
