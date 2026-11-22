"""Bounded, in-memory cache for FLY's authenticated, read-only market requests.

No API keys, account credentials, or simulated portfolio data are cached.
A failed provider request is never cached; cache resets on server restart.
"""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic


class MarketCache:
    def __init__(self, max_entries=64, clock=monotonic):
        if not 1 <= max_entries <= 256:
            raise ValueError("Invalid cache size")
        self.max_entries = max_entries
        self.clock = clock
        self._lock = RLock()
        self._values = OrderedDict()

    def get(self, key, ttl, loader):
        if ttl <= 0 or ttl > 3600:
            raise ValueError("Invalid cache TTL")
        with self._lock:
            now = self.clock()
            for existing in tuple(self._values):
                if self._values[existing][0] <= now:
                    del self._values[existing]
            if key in self._values:
                self._values.move_to_end(key)
                return deepcopy(self._values[key][1])
            result = loader()
            self._values[key] = (self.clock() + ttl, deepcopy(result))
            while len(self._values) > self.max_entries:
                self._values.popitem(last=False)
            return deepcopy(result)


MARKET_CACHE = MarketCache()
