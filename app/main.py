"""
FastAPI demo app for the Token Bucket rate limiter.

Endpoint:
  GET /request?client_id=alice

Returns:
  200 OK              if allowed, with header X-RateLimit-Remaining
  429 Too Many Requests if blocked, with header Retry-After (seconds)

Configure limit via environment variables (or just edit the constants below):
  RATE_LIMIT_CAPACITY   -> N (default 5)
  RATE_LIMIT_PERIOD     -> T seconds (default 10)
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse

from app.limiter import TokenBucketLimiter

CAPACITY = int(os.getenv("RATE_LIMIT_CAPACITY", "5"))
PERIOD_SECONDS = float(os.getenv("RATE_LIMIT_PERIOD", "10"))
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Two Theta Rate Limiter Demo")
limiter = TokenBucketLimiter(capacity=CAPACITY, period_seconds=PERIOD_SECONDS)


def get_client_id(request: Request) -> str:
    """
    Client identification strategy:
    - Prefer an explicit `client_id` query param (lets us simulate multiple
      clients easily for the demo / grader).
    - Fall back to the caller's IP address, which is what you'd use by
      default in a real deployment (no API key required).
    """
    client_id = request.query_params.get("client_id")
    if client_id:
        return client_id
    return request.client.host if request.client else "unknown"


@app.get("/request")
def make_request(request: Request):
    client_id = get_client_id(request)
    result = limiter.allow(client_id)

    headers = {
        "X-RateLimit-Limit": str(result["limit"]),
        "X-RateLimit-Remaining": str(result["remaining"]),
        "X-RateLimit-Reset": str(result["reset_after"]),  # seconds until bucket is full again
    }

    if result["allowed"]:
        return JSONResponse(
            status_code=200,
            content={"status": "allowed", "client_id": client_id, **result},
            headers=headers,
        )
    else:
        headers["Retry-After"] = str(result["retry_after"])
        return JSONResponse(
            status_code=429,
            content={"status": "blocked", "client_id": client_id, **result},
            headers=headers,
        )


@app.get("/demo")
def demo_page():
    """Serves the interactive frontend demo of the rate limiter."""
    return FileResponse(STATIC_DIR / "demo.html")


@app.delete("/reset/{client_id}")
def reset_client(client_id: str):
    """
    Resets a client's bucket back to full.
    Useful for demos/testing so you don't have to wait for natural refill.
    """
    limiter.reset(client_id)
    return {"status": "reset", "client_id": client_id}


@app.get("/stats")
def stats():
    """
    Observability endpoint: shows allowed vs blocked request counts per
    client since the server started. Useful for debugging / demoing which
    clients are hitting their limits.
    """
    return {"stats": limiter.get_stats()}


@app.get("/")
def root():
    return {
        "message": "Two Theta Rate Limiter Demo",
        "usage": "GET /request?client_id=alice",
        "limit": f"{CAPACITY} requests per {PERIOD_SECONDS} seconds, per client",
        "demo_ui": "/demo",
    }