import httpx
import time

BASE_URL = "http://127.0.0.1:8000/request"
print("Firing 8 rapid requests for alice...\n")
for i in range(1, 9):
    start = time.perf_counter()
    r = httpx.get(BASE_URL, params={"client_id": "alice"})
    elapsed = time.perf_counter() - start
    data = r.json()
    print(f"Req {i}: status={r.status_code} | remaining={data.get('remaining')} | "
          f"retry_after={data.get('retry_after')} | took={elapsed*1000:.1f}ms")