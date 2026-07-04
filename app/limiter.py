"""
Token Bucket Rate Limiter
-------------------------
Each client gets a "bucket" that holds up to `capacity` tokens.
- Every request consumes 1 token.
- Tokens refill continuously over time at rate = capacity / period_seconds.
- If a client has no tokens left, the request is blocked.

Why Token Bucket (vs fixed window / sliding window log / leaky bucket):
- Allows short controlled bursts (good for real APIs, e.g. a client that
  briefly sends a batch of requests isn't punished as harshly as fixed window).
- O(1) memory per client (just tokens + last_refill timestamp) — no need to
  store a log of every request timestamp (unlike sliding window log).
- No "edge burst" problem of fixed window, where a client can send N requests
  at the very end of one window and N more at the very start of the next,
  getting 2N requests in a short span.
- Trade-off: slightly more math than fixed window, and it's an approximation
  of a smooth rate rather than a hard log of exact request times (like sliding
  window log would give you, at the cost of more memory).
"""

import threading
import time
from dataclasses import dataclass


@dataclass
class BucketState:
    tokens: float
    last_refill: float


class TokenBucketLimiter:
    def __init__(self, capacity: int, period_seconds: float):
        """
        capacity: max requests allowed per period (N)
        period_seconds: the time window in seconds (T)
        e.g. capacity=5, period_seconds=10 -> "5 requests per 10 seconds"
        """
        if capacity <= 0 or period_seconds <= 0:
            raise ValueError("capacity and period_seconds must be > 0")

        self.capacity = capacity
        self.period_seconds = period_seconds
        self.refill_rate = capacity / period_seconds  # tokens added per second

        self._buckets: dict[str, BucketState] = {}
        self._stats: dict[str, dict] = {}
        self._lock = threading.Lock()  # protects the shared dict + bucket updates

    def _get_or_create_bucket(self, client_id: str, now: float) -> BucketState:
        bucket = self._buckets.get(client_id)
        if bucket is None:
            bucket = BucketState(tokens=float(self.capacity), last_refill=now)
            self._buckets[client_id] = bucket
        return bucket

    def _refill(self, bucket: BucketState, now: float) -> None:
        elapsed = now - bucket.last_refill
        if elapsed <= 0:
            return
        added = elapsed * self.refill_rate
        bucket.tokens = min(self.capacity, bucket.tokens + added)
        bucket.last_refill = now

    def allow(self, client_id: str) -> dict:
        """
        Returns a dict:
        {
            "allowed": bool,
            "remaining": int,          # tokens left AFTER this decision
            "retry_after": float,      # seconds until 1 token is available (0 if allowed)
            "limit": int,
            "period_seconds": float,
            "reset_after": float,      # seconds until bucket is FULLY refilled again
        }
        Thread-safe: a single lock guards read-modify-write per client so
        concurrent requests for the same client don't race and both succeed
        when only one should.
        """
        now = time.monotonic()
        with self._lock:
            bucket = self._get_or_create_bucket(client_id, now)
            self._refill(bucket, now)

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                reset_after = round((self.capacity - bucket.tokens) / self.refill_rate, 3)
                self._record_stat(client_id, allowed=True)
                return {
                    "allowed": True,
                    "remaining": int(bucket.tokens),
                    "retry_after": 0.0,
                    "limit": self.capacity,
                    "period_seconds": self.period_seconds,
                    "reset_after": reset_after,
                }
            else:
                # time until at least 1 token is available
                tokens_needed = 1 - bucket.tokens
                retry_after = round(tokens_needed / self.refill_rate, 3)
                reset_after = round((self.capacity - bucket.tokens) / self.refill_rate, 3)
                self._record_stat(client_id, allowed=False)
                return {
                    "allowed": False,
                    "remaining": 0,
                    "retry_after": retry_after,
                    "limit": self.capacity,
                    "period_seconds": self.period_seconds,
                    "reset_after": reset_after,
                }

    def _record_stat(self, client_id: str, allowed: bool) -> None:
        """Track allowed/blocked counts per client for the /stats endpoint."""
        stat = self._stats.setdefault(client_id, {"allowed": 0, "blocked": 0})
        if allowed:
            stat["allowed"] += 1
        else:
            stat["blocked"] += 1

    def get_stats(self) -> dict:
        """Returns a snapshot of per-client allow/block counts."""
        with self._lock:
            return {cid: dict(counts) for cid, counts in self._stats.items()}
        
    def reset(self, client_id: str) -> None:
        """Removes a client's bucket so it starts fresh (full) on next request."""
        with self._lock:
            self._buckets.pop(client_id, None)