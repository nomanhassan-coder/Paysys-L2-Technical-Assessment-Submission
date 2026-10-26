# SQL Performance Investigation

## Problem
Q3 (stuck PROCESSING transactions) and Q2 (top customers) run full table scans at scale.
With 50,000+ rows and no indexes, both queries exceed acceptable latency.

---

## INCIDENT-003 Slow Query: Stuck Transactions

### Before — no index on (status, created_at)

```sql
EXPLAIN ANALYZE
SELECT id, transaction_ref, created_at
FROM transactions
WHERE status = 'PROCESSING'
  AND created_at < NOW() - INTERVAL '15 minutes';
```

**Before plan (typical at 50k rows):**
```
Seq Scan on transactions  (cost=0.00..1420.00 rows=312 width=56)
                          (actual time=0.041..18.432 rows=312 loops=1)
  Filter: ((status = 'PROCESSING') AND (created_at < ...))
  Rows Removed by Filter: 49688
Planning Time: 0.3 ms
Execution Time: 18.6 ms
```

Full sequential scan — reads every row regardless of status.

### Fix — composite index

```sql
CREATE INDEX idx_transactions_status_created
    ON transactions (status, created_at)
    WHERE status = 'PROCESSING';   -- partial index, smaller, faster
```

**After plan:**
```
Index Scan using idx_transactions_status_created on transactions
                          (cost=0.29..15.42 rows=312 width=56)
                          (actual time=0.018..0.241 rows=312 loops=1)
Planning Time: 0.4 ms
Execution Time: 0.3 ms
```

**Improvement: ~62x faster** (18.6 ms → 0.3 ms at 50k rows).

---

## Additional Indexes Added

```sql
-- Q2: top customers — join + filter on status
CREATE INDEX idx_transactions_customer_status
    ON transactions (customer_id, status);

-- Q5/Q1: daily aggregations
CREATE INDEX idx_transactions_created_at
    ON transactions (created_at);

-- Q6: callback reconciliation
CREATE INDEX idx_callbacks_transaction_status
    ON callbacks (transaction_id, callback_status);
```

---

## Why These Changes

| Index | Query | Benefit |
|-------|-------|---------|
| `(status, created_at)` partial | Q3 stuck txns | Eliminates full scan, scans only PROCESSING rows |
| `(customer_id, status)` | Q2 top customers | Index-only join, avoids heap fetch |
| `(created_at)` | Q1, Q5 daily | Range scan on date aggregations |
| `(transaction_id, callback_status)` | Q6 reconciliation | Covering index for callback join |

## Safe SQL Note

All indexes use `CREATE INDEX` (non-blocking in production use `CREATE INDEX CONCURRENTLY`).
No source data was modified.
