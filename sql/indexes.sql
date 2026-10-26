-- Performance indexes for MiniPay transactions schema
-- Run after initial schema setup

-- Partial index: stuck PROCESSING query (Q3)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_status_created
    ON transactions (status, created_at)
    WHERE status = 'PROCESSING';

-- Composite index: top customers by success (Q2)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_customer_status
    ON transactions (customer_id, status);

-- Index: daily aggregations (Q1, Q5)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_created_at
    ON transactions (created_at);

-- Index: callback reconciliation (Q6)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_callbacks_transaction_status
    ON callbacks (transaction_id, callback_status);

-- Index: duplicate detection (Q4) — already has UNIQUE on transaction_ref? No.
-- transaction_ref has no unique constraint in base schema, add index for GROUP BY
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_ref
    ON transactions (transaction_ref);
