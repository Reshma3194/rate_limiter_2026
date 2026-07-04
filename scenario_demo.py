"""
Reproduces the exact "Sample Scenario" from the assignment:

    Configure: 5 requests per 10 seconds, per client.
    Client "alice" sends 8 requests in the first 3 seconds,
    then waits 10 seconds, then sends 2 more requests.

Run directly (no server needed -- uses the limiter class in-process):
    python scenario_demo.py
"""

import time

from app.limiter import TokenBucketLimiter


def run():
    limiter = TokenBucketLimiter(capacity=5, period_seconds=10)

    print("Config: 5 requests / 10 seconds, per client\n")
    print("--- Phase 1: alice sends 8 requests in the first 3 seconds ---")
    for i in range(1, 9):
        result = limiter.allow("alice")
        status = "ALLOWED" if result["allowed"] else "BLOCKED"
        extra = "" if result["allowed"] else f"(retry after {result['retry_after']}s)"
        print(f"  Request {i}: {status}  remaining={result['remaining']} {extra}")
        time.sleep(3 / 8)  # spread 8 requests across ~3 seconds

    print("\n--- Phase 2: alice waits 10 seconds ---")
    time.sleep(10)
    print("  (waited 10s -- bucket should be fully refilled)")

    print("\n--- Phase 3: alice sends 2 more requests ---")
    for i in range(1, 3):
        result = limiter.allow("alice")
        status = "ALLOWED" if result["allowed"] else "BLOCKED"
        print(f"  Request {i}: {status}  remaining={result['remaining']}")

    print("\nDone. This matches the token bucket design: bursts up to the")
    print("bucket capacity are allowed immediately, then blocked until tokens")
    print("refill continuously (not all-or-nothing) over the configured period.")


if __name__ == "__main__":
    run()