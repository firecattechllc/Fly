import unittest
from market_cache import MarketCache

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.now=[0.0]
        self.cache=MarketCache(max_entries=2,clock=lambda:self.now[0])

    def test_hits_and_expiration(self):
        calls=[]
        def loader():
            calls.append(1)
            return {"bars":[{"close":42.0}]}
        first=self.cache.get(("SPY",),30,loader)
        first["bars"][0]["close"]=999
        cached=self.cache.get(("SPY",),30,loader)
        self.assertEqual(cached["bars"][0]["close"],42.0)
        self.assertEqual(len(calls),1)
        self.now[0]=30.1
        self.cache.get(("SPY",),30,loader)
        self.assertEqual(len(calls),2)

    def test_failure_is_never_cached(self):
        calls=[]
        def fail():
            calls.append("called")
            raise RuntimeError("provider down")
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                self.cache.get(("X",),20,fail)
        self.assertEqual(len(calls),2)

    def test_oldest_entry_evicted_at_capacity(self):
        counts={}
        def fetch(key):
            def run():
                counts[key]=counts.get(key,0)+1
                return {"symbol":key}
            return run
        for key in ("A","B","C","A"):
            self.cache.get((key,),20,fetch(key))
        self.assertEqual(counts,{"A":2,"B":1,"C":1})

    def test_returns_are_isolated_by_key(self):
        for key in (("bars","AAPL",90,"iex"),("bars","AAPL",30,"iex")):
            value=self.cache.get(key,40,lambda key=key:{"lookback":key[2]})
            self.assertEqual(value["lookback"],key[2])

    def test_bad_ttl_rejected(self):
        for ttl in (0,-1,3601):
            with self.assertRaises(ValueError):
                self.cache.get("key",ttl,lambda:None)

if __name__=="__main__":
    unittest.main()
