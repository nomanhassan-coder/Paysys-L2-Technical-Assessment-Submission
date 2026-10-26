# INCIDENT-003 RCA — Transaction Search Performance Degradation

**Priority:** P2  
**Status:** Resolved  
**Date:** 2026-10-22

---

## Summary

Transaction investigation queries used a sequential scan before indexing. On the captured 60,000-row sample, the stuck-transaction query took about 20 ms; this is a measured baseline, not a multi-second production claim.

---

## Data Generation

```bash
python database/generate_data.py > seed.sql
psql minipay < seed.sql
# Generated: 50,000 transactions, 1,000 customers, with callback volume determined by the seeded statuses
```

---

## Slow Query Identified

Query for stuck PROCESSING transactions (used by L2 support tool and ops dashboard):

```sql
SELECT id, transaction_ref, customer_id, amount, created_at
FROM transactions
WHERE status = 'PROCESSING'
  AND created_at < NOW() - INTERVAL '15 minutes';
```

---

## Evidence — Before Index

```sql
EXPLAIN (ANALYZE, BUFFERS) 
SELECT id, transaction_ref, created_at
FROM transactions
WHERE status = 'PROCESSING'
  AND created_at < NOW() - INTERVAL '15 minutes';
```

```
Seq Scan on transactions  
  (cost=0.00..1587.00 rows=298 width=56)  
  (actual time=0.051..19.832 rows=298 loops=1)
  Filter: ((status = 'PROCESSING') AND (created_at < '...'))
  Rows Removed by Filter: 59702
  Buffers: shared hit=687
Planning Time: 0.4 ms
Execution Time: 20.1 ms
```

**Full sequential scan. Reads all 60,000 rows to return 298. The exact timing depends on hardware and cache state.**

---

## Fix Applied

```sql
-- Partial index: only indexes PROCESSING rows (small, targeted)
CREATE INDEX CONCURRENTLY idx_transactions_status_created
    ON transactions (status, created_at)
    WHERE status = 'PROCESSING';
```

---

## Evidence — After Index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, transaction_ref, created_at
FROM transactions
WHERE status = 'PROCESSING'
  AND created_at < NOW() - INTERVAL '15 minutes';
```

```
Index Scan using idx_transactions_status_created on transactions
  (cost=0.28..18.73 rows=298 width=56)
  (actual time=0.015..0.287 rows=298 loops=1)
  Buffers: shared hit=12
Planning Time: 0.5 ms
Execution Time: 0.3 ms
```

---

## Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Execution time | 20.1 ms | 0.3 ms | **67x faster** |
| Buffer hits | 687 | 12 | 98% fewer reads |
| Rows scanned | 60,000 | 298 | Only relevant rows |

---

## Additional Indexes

See `sql/indexes.sql` for full set covering Q2, Q5, Q6 patterns.

---

## Preventive Controls

1. **Schema review:** Any query with `WHERE status =` or `WHERE created_at <` needs index assessment before merge.
2. **Slow query log:** Enable `log_min_duration_statement = 100` in PostgreSQL; alert on queries >500ms.
3. **Load test in CI:** Run EXPLAIN ANALYZE on critical queries against 100k-row seed data as part of CI pipeline.
4. **`pg_stat_user_tables`:** Monitor `seq_scan` count in weekly ops review; high seq scans signal missing indexes.
