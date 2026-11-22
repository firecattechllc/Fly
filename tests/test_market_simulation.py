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
  h={'AAPL':history([('2026-01-02',110),('2026-01-03',121)]),
     'SPY':history([('2026-01-01',100),('2026-01-02',105),('2026-01-03',110)])}
  r=calculate(self.db,h)
  self.assertEqual(r['status'],'DAILY_MARKET_REPLAY')
  self.assertAlmostEqual(r['daily_time_weighted_return_pct'],21.0,places=3)
  self.assertEqual(r['observations'],2)
  self.assertAlmostEqual(r['benchmark_time_weighted_return_pct'],10.0,places=3)
  self.assertAlmostEqual(r['active_return_pct'],11.0,places=3)
  self.assertEqual(len(r['monthly_returns']),1)
  self.assertEqual(len(r['quarterly_returns']),1)
  self.assertEqual(r['contribution_attribution'][0]['symbol'],'AAPL')
  self.assertEqual(r['scenario_comparison']['status'],'INSUFFICIENT_DATA')
  self.assertIsNotNone(r['risk_metrics']['portfolio_annualized_volatility_pct'])
  self.assertIsNone(r['points'][-1]['rolling_20d_volatility_pct'])
  self.assertEqual(r['tear_sheet']['position_count'],1)
 def test_missing_symbol_fails_closed(self):
  r=calculate(self.db,{'AAPL':history([('2026-01-02',110)])})
  self.assertEqual(r['status'],'MISSING_SYMBOL_HISTORY')
 def test_cash_mismatch_fails_closed(self):
  self.db.execute('UPDATE account SET cash=500')
  r=calculate(self.db,{'AAPL':history([('2026-01-02',110)]),'SPY':history([('2026-01-01',100),('2026-01-02',105)])})
  self.assertEqual(r['status'],'RECONCILIATION_REQUIRED')
 def test_rolling_volatility_requires_and_uses_twenty_sessions(self):
  from datetime import date,timedelta
  days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(22)]
  aapl=[{"timestamp":d+"T21:00:00Z","close":100+i} for i,d in enumerate(days[1:])]
  spy=[{"timestamp":d+"T21:00:00Z","close":100+i*0.4} for i,d in enumerate(days)]
  self.db.execute("UPDATE positions SET last_cents=12000 WHERE symbol='AAPL'")
  r=calculate(self.db,{"AAPL":{"bars":aapl},"SPY":{"bars":spy}})
  self.assertEqual(r["status"],"DAILY_MARKET_REPLAY")
  self.assertIsNotNone(r["points"][-1]["rolling_20d_volatility_pct"])
  self.assertIsNotNone(r["points"][-1]["benchmark_rolling_20d_volatility_pct"])
if __name__=='__main__':unittest.main()
