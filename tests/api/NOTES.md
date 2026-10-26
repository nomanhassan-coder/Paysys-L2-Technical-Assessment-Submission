# API Test Notes — Timeouts, Retries, Idempotency, Error Handling

## Running the suite

```bash
pip install pytest requests
MINIPAY_API_URL=http://localhost:5000 MINIPAY_API_KEY=changeme pytest tests/api/ -v
```

---

## Client/Server Timeouts

**Client side:** Always set an explicit `timeout` on every request (connect + read). Without it, a hung upstream hangs the thread indefinitely.

```python
requests.get(url, timeout=(3, 10))  # 3s connect, 10s read
```

**Server side:** In Flask/Gunicorn, set `--timeout 30`. Behind a load balancer, set `proxy_read_timeout` to match. For DB calls, set `connect_timeout` and `statement_timeout` in the DSN.

**In payment integrations:** Timeouts on payment calls are ambiguous — the processor may or may not have processed the payment. Always treat timeout as "unknown state", not failure. Log the transaction ref for reconciliation.

---

## Retries

Never retry non-idempotent calls (plain `POST /payments`) without a unique `transaction_ref`. With an idempotent ref, retry is safe — the server returns the existing transaction.

Use exponential backoff with jitter:

```python
for attempt in range(3):
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code < 500:
            break
    except requests.exceptions.Timeout:
        if attempt == 2:
            raise
    time.sleep((2 ** attempt) + random.uniform(0, 1))
```

---

## Idempotency

`POST /api/payments` accepts a `transaction_ref`. If the same ref is submitted twice:
- First call: `201 Created`
- Subsequent calls: `200 OK` with the same record

This allows clients to safely retry on timeout without double-charging. The client must generate and persist the ref before the first attempt.

---

## HTTP 4xx vs 5xx

| Code | Meaning | Client action |
|------|---------|---------------|
| 400 | Bad request (validation failed) | Fix payload — do not retry |
| 401 | Unauthorized | Check API key — do not retry |
| 404 | Not found | Record does not exist — do not retry |
| 409 | Conflict (duplicate) | Already exists — treat as success or investigate |
| 429 | Rate limited | Back off and retry after `Retry-After` header |
| 500 | Server error | May retry with backoff; alert ops if persistent |
| 502/503 | Upstream unavailable | Retry; trigger circuit breaker after N failures |
| 504 | Gateway timeout | Payment state unknown — reconcile; do not duplicate |
