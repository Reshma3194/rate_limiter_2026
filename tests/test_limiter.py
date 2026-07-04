import threading
import time

import pytest

from app.limiter import TokenBucketLimiter


def test_allowed_under_limit():
    """All requests within the limit should be allowed."""
    limiter = TokenBucketLimiter(capacity=5, period_seconds=10)
    for i in range(5):
        result = limiter.allow("alice")
        assert result["allowed"] is True, f"request {i+1} should be allowed"
    assert result["remaining"] == 0


def test_blocked_over_limit():
    """The request beyond the limit should be blocked."""
    limiter = TokenBucketLimiter(capacity=5, period_seconds=10)
    for _ in range(5):
        limiter.allow("alice")
    result = limiter.allow("alice")  # 6th request
    assert result["allowed"] is False
    assert result["retry_after"] > 0


def test_bucket_refills_over_time():
    """After waiting, tokens should refill and requests should be allowed again."""
    limiter = TokenBucketLimiter(capacity=5, period_seconds=1)  # fast refill for test speed
    for _ in range(5):
        limiter.allow("alice")
    blocked = limiter.allow("alice")
    assert blocked["allowed"] is False

    time.sleep(1.1)  # wait longer than the full period -> bucket should be full again

    result = limiter.allow("alice")
    assert result["allowed"] is True


def test_per_client_isolation_edge_case():
    """One client using up their quota must not affect another client (edge case)."""
    limiter = TokenBucketLimiter(capacity=5, period_seconds=10)
    for _ in range(5):
        limiter.allow("alice")
    alice_blocked = limiter.allow("alice")
    bob_result = limiter.allow("bob")

    assert alice_blocked["allowed"] is False
    assert bob_result["allowed"] is True  # bob has his own full bucket


def test_concurrent_requests_same_client_edge_case():
    """
    Edge case: many threads hit allow() for the SAME client at almost the
    same instant. Exactly `capacity` should be allowed, never more -- this
    verifies the lock prevents a race condition (double-spending tokens).
    """
    limiter = TokenBucketLimiter(capacity=5, period_seconds=10)
    results = []
    results_lock = threading.Lock()

    def fire():
        r = limiter.allow("alice")
        with results_lock:
            results.append(r["allowed"])

    threads = [threading.Thread(target=fire) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed_count = sum(1 for r in results if r is True)
    assert allowed_count == 5, "exactly capacity requests should be allowed under a race"   