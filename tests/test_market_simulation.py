import json
import sqlite3
import unittest
from market_simulation import calculate

def history(values):
 return {'bars':[{'timestamp':d+'T21:00:00Z','close':v} for d,v in values]}

class MarketSimulationTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.execute('CREATE TABLE simulation_baseline(id INTEGER,created_utc TEXT,cash_cents INTEGER,positions_json TEXT)')
  self.db.execute('CREATE TABLE transactions(id INTEGER,created_utc TEXT,symbol TEXT,side TEXT,qty INTEGER,price_cents INTEGER,notional_cents INTEGER)')
  self.db.execute('CREATE TABLE account(id INTEGER,cash INTEGER)')
  self.db.execute('CREATE TABLE positions(symbol TEXT,qty INTEGER,last_cents INTEGER)')
  self.db.execute('INSERT INTO simulation_baseline VALUES(1,?,?,?)',('2026-01-01T00:00:00+00:00',10000,json.dumps([{'symbol':'AAPL','qty':1,'last_cents':10000}])))
  self.db.execute("INSERT INTO transactions VALUES(1,'2026-01-02T15:00:00+00:00','AAPL','BUY',1,10000,10000)")
  self.db.execute('INSERT INTO account VALUES(1,0)')
  self.db.execute("INSERT INTO positions VALUES('AAPL',2,12100)")
 def test_daily_twr_and_drawdown(self):
  h={'AAPL':history([('2026-01-02',110),('2026-01-03',121)])}
  r=calculate(self.db,h)
  self.assertEqual(r['status'],'DAILY_MARKET_REPLAY')
  self.assertAlmostEqual(r['daily_time_weighted_return_pct'],21.0,places=3)
  self.assertEqual(r['observations'],2)
 def test_missing_symbol_fails_closed(self):
  r=calculate(self.db,{})
  self.assertEqual(r['status'],'MISSING_SYMBOL_HISTORY')
 def test_cash_mismatch_fails_closed(self):
  self.db.execute('UPDATE account SET cash=500')
  r=calculate(self.db,{'AAPL':history([('2026-01-02',110)])})
  self.assertEqual(r['status'],'RECONCILIATION_REQUIRED')
if __name__=='__main__':unittest.main()
