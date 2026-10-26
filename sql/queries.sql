-- MiniPay SQL Investigation Queries
-- Schema: customers, transactions, callbacks

-- ============================================================
-- Q1: Transaction count and total value by status and day
-- ============================================================
SELECT
    DATE(created_at)          AS txn_day,
    status,
    COUNT(*)                  AS txn_count,
    SUM(amount)               AS total_value
FROM transactions
GROUP BY DATE(created_at), status
ORDER BY txn_day DESC, status;


-- ============================================================
-- Q2: Top 10 customers by successful transaction value
-- ============================================================
SELECT
    c.customer_ref,
    c.name,
    COUNT(t.id)               AS success_count,
    SUM(t.amount)             AS total_value
FROM customers c
JOIN transactions t ON t.customer_id = c.id
WHERE t.status = 'SUCCESS'
GROUP BY c.id, c.customer_ref, c.name
ORDER BY total_value DESC
LIMIT 10;


-- ============================================================
-- Q3: Transactions stuck in PROCESSING > 15 minutes
-- ============================================================
SELECT
    id,
    transaction_ref,
    customer_id,
    amount,
    created_at,
    EXTRACT(EPOCH FROM (NOW() - created_at)) / 60  AS minutes_stuck
FROM transactions
WHERE status = 'PROCESSING'
  AND created_at < NOW() - INTERVAL '15 minutes'
ORDER BY created_at ASC;


-- ============================================================
-- Q4: Duplicate transaction references
-- ============================================================
SELECT
    transaction_ref,
    COUNT(*)        AS duplicate_count,
    MIN(id)         AS first_id,
    MAX(id)         AS last_id,
    MIN(created_at) AS first_seen,
    MAX(created_at) AS last_seen
FROM transactions
GROUP BY transaction_ref
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;


-- ============================================================
-- Q5: Daily success rate as a percentage
-- ============================================================
SELECT
    DATE(created_at)                                                  AS txn_day,
    COUNT(*)                                                          AS total_txns,
    COUNT(*) FILTER (WHERE status = 'SUCCESS')                        AS success_count,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'SUCCESS') * 100.0 / COUNT(*),
        2
    )                                                                 AS success_rate_pct
FROM transactions
GROUP BY DATE(created_at)
ORDER BY txn_day DESC;


-- ============================================================
-- Q6: Reconciliation — SUCCESS transactions vs callback SUCCESS
-- ============================================================
WITH txn_success AS (
    SELECT COUNT(*) AS txn_count, SUM(amount) AS txn_value
    FROM transactions
    WHERE status = 'SUCCESS'
),
callback_success AS (
    SELECT COUNT(DISTINCT c.transaction_id) AS cb_count,
           SUM(t.amount)                    AS cb_value
    FROM callbacks c
    JOIN transactions t ON t.id = c.transaction_id
    WHERE c.callback_status = 'SUCCESS'
)
SELECT
    ts.txn_count,
    ts.txn_value,
    cs.cb_count,
    cs.cb_value,
    (ts.txn_count - cs.cb_count)    AS count_gap,
    (ts.txn_value - cs.cb_value)    AS value_gap
FROM txn_success ts, callback_success cs;


-- ============================================================
-- Q7: Average and p95 processing time (completed transactions)
-- ============================================================
SELECT
    status,
    COUNT(*)                                                                  AS count,
    ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))), 2)           AS avg_seconds,
    ROUND(
        PERCENTILE_CONT(0.95) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (completed_at - created_at))
        ), 2
    )                                                                         AS p95_seconds
FROM transactions
WHERE completed_at IS NOT NULL
GROUP BY status;
