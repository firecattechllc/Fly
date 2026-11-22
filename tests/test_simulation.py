import sqlite3
import unittest
from simulation import ensure_baseline,replay

class SimulationTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.execute('CREATE TABLE account(id INTEGER PRIMARY KEY,cash INTEGER)')
  self.db.execute('CREATE TABLE positions(symbol TEXT,qty INTEGER,last_cents INTEGER)')
  self.db.execute('CREATE TABLE transactions(id INTEGER PRIMARY KEY,created_utc TEXT,symbol TEXT,side TEXT,qty INTEGER,price_cents INTEGER,notional_cents INTEGER)')
  self.db.execute('INSERT INTO account VALUES(1,100000)')
  self.db.execute("INSERT INTO positions VALUES('AAPL',2,10000)")
  ensure_baseline(self.db)
 def test_baseline_and_buy_sell_replay_reconcile(self):
  self.db.execute("INSERT INTO transactions VALUES(1,'2026-01-02T10:00:00Z','AAPL','BUY',1,10000,10000)")
  self.db.execute('UPDATE account SET cash=90000')
  self.db.execute('UPDATE positions SET qty=3,last_cents=10000')
  result=replay(self.db)
  self.assertEqual(result['status'],'RECONCILED_EVENT_REPLAY')
  self.assertEqual(result['observations'],2)
  self.assertEqual(result['equity_change_cents'],0)
 def test_mismatch_never_publishes_performance(self):
  self.db.execute('UPDATE account SET cash=1')
  result=replay(self.db)
  self.assertEqual(result['status'],'RECONCILIATION_REQUIRED')
 def test_existing_baseline_is_not_overwritten(self):
  ensure_baseline(self.db)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM simulation_baseline').fetchone()[0],1)
if __name__=='__main__':unittest.main()
