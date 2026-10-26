CREATE TABLE customers (
  id BIGSERIAL PRIMARY KEY,
  customer_ref VARCHAR(40) NOT NULL UNIQUE,
  name VARCHAR(120) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE transactions (
  id BIGSERIAL PRIMARY KEY,
  transaction_ref VARCHAR(50) NOT NULL,
  customer_id BIGINT NOT NULL REFERENCES customers(id),
  amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
  status VARCHAR(20) NOT NULL CHECK (status IN ('PROCESSING','SUCCESS','FAILED')),
  created_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP NULL,
  failure_code VARCHAR(40) NULL
);

CREATE TABLE callbacks (
  id BIGSERIAL PRIMARY KEY,
  transaction_id BIGINT NOT NULL REFERENCES transactions(id),
  attempt_no INTEGER NOT NULL,
  http_status INTEGER NULL,
  callback_status VARCHAR(20) NOT NULL CHECK (callback_status IN ('SUCCESS','FAILED')),
  attempted_at TIMESTAMP NOT NULL,
  UNIQUE(transaction_id, attempt_no)
);

-- Intentionally minimal indexing. Assess indexes based on workload.
