"""Generate PostgreSQL-compatible INSERT statements with synthetic MiniPay data.
Usage: python generate_data.py > seed.sql
"""
import random
from datetime import datetime, timedelta

random.seed(42)
N_CUSTOMERS = 1000
N_TX = 50000
base = datetime(2026, 9, 1, 0, 0, 0)


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


print("BEGIN;")
for i in range(1, N_CUSTOMERS + 1):
    print(f"INSERT INTO customers(customer_ref,name) VALUES ('CUST{i:06d}','Customer {i}');")

for i in range(1, N_TX + 1):
    # A small set of duplicate refs is intentional for investigation.
    ref_num = i if i % 5000 else i - 1
    ref = f"TXN{ref_num:08d}"
    cust = random.randint(1, N_CUSTOMERS)
    amount = round(random.uniform(100, 100000), 2)
    created = base + timedelta(seconds=random.randint(0, 10 * 86400))
    r = random.random()
    if r < 0.82:
        status = "SUCCESS"
        completed = created + timedelta(seconds=random.randint(1, 90))
        failure = "NULL"
    elif r < 0.95:
        status = "FAILED"
        completed = created + timedelta(seconds=random.randint(1, 120))
        failure = "'UPSTREAM_ERROR'"
    else:
        status = "PROCESSING"
        completed = None
        failure = "NULL"
    completed_sql = f"'{ts(completed)}'" if completed else "NULL"
    print(
        "INSERT INTO transactions(transaction_ref,customer_id,amount,status,created_at,completed_at,failure_code) "
        f"VALUES ('{ref}',{cust},{amount},'{status}','{ts(created)}',{completed_sql},{failure});"
    )
    if status in ("SUCCESS", "FAILED"):
        cb_success = status == "SUCCESS" and random.random() < 0.94
        attempts = 1 if cb_success else random.randint(1, 3)
        for a in range(1, attempts + 1):
            ok = cb_success and a == attempts
            http = 200 if ok else random.choice([500, 502, 503])
            cbs = "SUCCESS" if ok else "FAILED"
            attempted = (completed or created) + timedelta(seconds=a * 5)
            print(
                "INSERT INTO callbacks(transaction_id,attempt_no,http_status,callback_status,attempted_at) "
                f"VALUES ({i},{a},{http},'{cbs}','{ts(attempted)}');"
            )
print("COMMIT;")
