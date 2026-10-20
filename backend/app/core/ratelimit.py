import time
from collections import deque
from threading import Lock


class SlidingWindowLimiter:
    """In-process sliding-window counter.

    Good enough for a single API process. When running several workers behind a load balancer,
    move this to a shared store (e.g. Redis) so limits apply across processes.
    """

    def __init__(self, max_hits: int, window_seconds: int, max_keys: int = 50_000) -> None:
        self.max_hits = max_hits
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _prune(self, q: deque[float], now: float) -> None:
        cutoff = now - self.window
        while q and q[0] <= cutoff:
            q.popleft()

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return False
            self._prune(q, now)
            return len(q) >= self.max_hits

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) >= self.max_keys and key not in self._hits:
                # Bound memory: drop keys whose windows have fully expired.
                for k in [k for k, q in self._hits.items() if not q or q[-1] <= now - self.window]:
                    del self._hits[k]
            q = self._hits.setdefault(key, deque())
            self._prune(q, now)
            q.append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
