"""
MiniPay API — Flask application
Routes: POST /api/customers, POST /api/payments, GET /api/payments/{id},
        GET /api/customers/{id}/payments, GET /health
"""

import os
import logging
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify, g, render_template_string, session, redirect, url_for
import psycopg2
import psycopg2.extras
import psycopg2.pool

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("minipay.api")

app = Flask(__name__)
app.config["API_KEY"] = os.environ.get("API_KEY", "changeme")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "local-development-secret")

# ---------------------------------------------------------------------------
# DB connection pool
# ---------------------------------------------------------------------------
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", 5432)),
            dbname=os.environ.get("DB_NAME", "minipay"),
            user=os.environ.get("DB_USER", "minipay"),
            password=os.environ.get("DB_PASSWORD", ""),
            connect_timeout=5,
        )
    return _pool


def get_db():
    if "db" not in g:
        g.db = get_pool().getconn()
        g.db.autocommit = False
    return g.db


@app.teardown_appcontext
def release_db(exc):
    db = g.pop("db", None)
    if db is not None:
        try:
            if exc:
                db.rollback()
            else:
                db.commit()
        finally:
            get_pool().putconn(db)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Api-Key") or request.args.get("api_key")
        if key != app.config["API_KEY"]:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
TXN_REF_PATTERN = r"^[A-Z0-9_-]{6,50}$"
import re


def _row(cursor) -> dict | None:
    row = cursor.fetchone()
    return dict(row) if row else None


def _rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _serialize_dict(d: dict) -> dict:
    return {k: _serialize(v) for k, v in d.items()}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify({"status": "ok", "db": "ok"}), 200
    except Exception as exc:
        log.error("Health check failed: %s", exc)
        return jsonify({"status": "degraded", "db": "error"}), 503


@app.get("/health/live")
def health_live():
    return jsonify({"status": "ok"}), 200


@app.get("/health/ready")
def health_ready():
    return health()


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
@app.post("/api/customers")
@require_api_key
def create_customer():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    customer_ref = data.get("customer_ref") or f"CUST-{uuid.uuid4().hex[:12].upper()}"
    db = get_db()
    try:
        with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO customers (customer_ref, name) VALUES (%s, %s) RETURNING *",
                (customer_ref, name),
            )
            row = _row(cur)
        db.commit()
        return jsonify(_serialize_dict(row)), 201
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        return jsonify({"error": "customer_ref already exists"}), 409
    except Exception as exc:
        db.rollback()
        log.error("create_customer error: %s", exc)
        return jsonify({"error": "internal error"}), 500


@app.get("/api/customers/<int:customer_id>")
@require_api_key
def get_customer(customer_id: int):
    db = get_db()
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM customers WHERE id = %s", (customer_id,))
        row = _row(cur)
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(_serialize_dict(row)), 200


@app.get("/api/customers/<int:customer_id>/payments")
@require_api_key
def list_customer_payments(customer_id: int):
    db = get_db()
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id FROM customers WHERE id = %s", (customer_id,))
        if not cur.fetchone():
            return jsonify({"error": "customer not found"}), 404
        cur.execute(
            "SELECT * FROM transactions WHERE customer_id = %s ORDER BY created_at DESC LIMIT 100",
            (customer_id,),
        )
        rows = _rows(cur)
    return jsonify([_serialize_dict(r) for r in rows]), 200


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
@app.post("/api/payments")
@require_api_key
def create_payment():
    data = request.get_json(silent=True) or {}
    errors = {}
    customer_id = data.get("customer_id")
    amount = data.get("amount")
    raw_ref = data.get("transaction_ref")
    transaction_ref = raw_ref.strip() if isinstance(raw_ref, str) else ""

    if not customer_id:
        errors["customer_id"] = "required"
    if amount is None:
        errors["amount"] = "required"
    elif not isinstance(amount, (int, float)) or amount <= 0:
        errors["amount"] = "must be positive number"
    if transaction_ref and not re.match(TXN_REF_PATTERN, transaction_ref):
        errors["transaction_ref"] = "invalid format (A-Z0-9_- 6-50 chars)"
    if errors:
        return jsonify({"error": "validation failed", "fields": errors}), 400
    try:
        requested_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return jsonify({"error": "validation failed", "fields": {"amount": "must be a valid number"}}), 400

    if not transaction_ref:
        transaction_ref = f"TXN-{uuid.uuid4().hex[:12].upper()}"

    db = get_db()
    try:
        with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Idempotency: return existing if ref already exists
            cur.execute(
                "SELECT * FROM transactions WHERE transaction_ref = %s",
                (transaction_ref,),
            )
            existing = _row(cur)
            if existing:
                if existing["customer_id"] != customer_id or Decimal(existing["amount"]) != requested_amount:
                    return jsonify({"error": "transaction_ref already exists with different payment details"}), 409
                return jsonify(_serialize_dict(existing)), 200

            cur.execute("SELECT id FROM customers WHERE id = %s", (customer_id,))
            if not cur.fetchone():
                return jsonify({"error": "customer not found"}), 404

            cur.execute(
                """INSERT INTO transactions
                   (transaction_ref, customer_id, amount, status, created_at)
                   VALUES (%s, %s, %s, 'PROCESSING', %s)
                   RETURNING *""",
                (transaction_ref, customer_id, requested_amount, datetime.now(timezone.utc)),
            )
            row = _row(cur)
        db.commit()
        return jsonify(_serialize_dict(row)), 201
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM transactions WHERE transaction_ref = %s", (transaction_ref,))
            existing = _row(cur)
        if existing and existing["customer_id"] == customer_id and Decimal(existing["amount"]) == requested_amount:
            return jsonify(_serialize_dict(existing)), 200
        return jsonify({"error": "transaction_ref already exists with different payment details"}), 409
    except Exception as exc:
        db.rollback()
        log.error("create_payment error: %s", exc)
        return jsonify({"error": "internal error"}), 500


@app.get("/api/payments/<transaction_ref>")
@require_api_key
def get_payment(transaction_ref: str):
    if not re.match(TXN_REF_PATTERN, transaction_ref):
        return jsonify({"error": "Invalid transaction reference format"}), 400

    db = get_db()
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM transactions WHERE transaction_ref = %s",
            (transaction_ref,),
        )
        row = _row(cur)
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(_serialize_dict(row)), 200


# ---------------------------------------------------------------------------
# Minimal operator UI
# ---------------------------------------------------------------------------
UI_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>MiniPay {{ title }}</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#172033;background:#f4f7fb}
*{box-sizing:border-box}body{margin:0;min-height:100vh}
.shell{max-width:980px;margin:0 auto;padding:2rem 1.25rem}
header{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:2rem}
.brand{display:flex;align-items:center;gap:.7rem}.brand-mark{display:grid;place-items:center;width:2.5rem;height:2.5rem;border-radius:.75rem;background:#2563eb;color:#fff;font-weight:800}
h1{font-size:1.35rem;margin:0}nav{display:flex;gap:.5rem;flex-wrap:wrap}
nav a{color:#334155;text-decoration:none;padding:.55rem .8rem;border-radius:.55rem;font-weight:600}
nav a:hover,nav a:focus{background:#e2e8f0;color:#1d4ed8}
main{background:#fff;border:1px solid #e2e8f0;border-radius:1rem;padding:2rem;box-shadow:0 12px 30px rgba(15,23,42,.06)}
.eyebrow{color:#2563eb;font-size:.78rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;margin:0 0 .5rem}
h2{font-size:1.65rem;margin:.25rem 0 .5rem}p{color:#64748b;line-height:1.55}
.form-card{max-width:560px}.field{margin:1rem 0}label{display:block;color:#334155;font-size:.9rem;font-weight:700;margin-bottom:.4rem}
input{display:block;width:100%;padding:.75rem .85rem;border:1px solid #cbd5e1;border-radius:.55rem;background:#fff;color:#172033;font-size:1rem}
input:focus{outline:3px solid #bfdbfe;border-color:#2563eb}
button{border:0;border-radius:.55rem;padding:.75rem 1rem;background:#2563eb;color:#fff;font-size:.95rem;font-weight:700;cursor:pointer}
button:hover,button:focus{background:#1d4ed8}.error,.success{margin:1rem 0;padding:.8rem 1rem;border-radius:.55rem;font-weight:600}
.error{color:#991b1b;background:#fef2f2;border:1px solid #fecaca}.success{color:#166534;background:#f0fdf4;border:1px solid #bbf7d0}
.search-result{margin-top:1.5rem;padding:1rem;border-radius:.7rem;background:#f8fafc;border:1px solid #e2e8f0}
pre{white-space:pre-wrap;overflow:auto;color:#334155}
@media(max-width:640px){.shell{padding:1rem}.header{align-items:flex-start}header{display:block}nav{margin-top:1rem}main{padding:1.25rem}}
</style></head>
<body><div class="shell"><header><div class="brand"><div class="brand-mark">M</div><h1>MiniPay</h1></div>
<nav><a href="/ui">Search</a><a href="/ui/payments/new">New payment</a><a href="/ui/login">Login</a></nav></header>
<main>{{ body|safe }}</main></div></body></html>"""


def _ui(body: str, title: str = "Operator Console"):
    return render_template_string(UI_PAGE, body=body, title=title)


@app.get("/ui")
def ui_home():
    ref = request.args.get("transaction_ref")
    result = ""
    if ref:
        with app.test_request_context(
            f"/api/payments/{ref}",
            headers={"X-Api-Key": session.get("api_key", app.config["API_KEY"])},
        ):
            response = get_payment(ref)
        payload = response[0].get_json()
        if response[1] == 200:
            result = f"<section class='search-result' data-testid='search-result'><h2>Transaction found</h2><pre>{payload}</pre></section>"
        else:
            result = "<section class='search-result' data-testid='search-result'><p>Transaction not found.</p></section>"
    body = f"""<div class="form-card"><p class="eyebrow">Operations console</p><h2>Find a transaction</h2>
    <p>Search by transaction reference to inspect payment status and processing details.</p>
    <form method="get"><div class="field"><label for="transaction-ref">Transaction ref</label>
    <input id="transaction-ref" name="transaction_ref" placeholder="Transaction ref" required>
    </div><button type="submit">Search transaction</button></form>{result}</div>"""
    return _ui(body)


@app.route("/ui/login", methods=["GET", "POST"])
def ui_login():
    message = ""
    if request.method == "POST":
        key = request.form.get("api_key", "")
        if key != app.config["API_KEY"]:
            message = "<p class='error'>Invalid API key.</p>"
        else:
            session["api_key"] = key
            return redirect(url_for("ui_home"))
    body = f"""<div class="form-card"><p class="eyebrow">Secure access</p><h2>Sign in</h2>
    <p>Use your MiniPay API key to access operator actions.</p>{message}
    <form method="post"><div class="field"><label for="api-key">API key</label>
    <input id="api-key" name="api_key" type="password" aria-label="API key" required>
    </div><button type="submit">Sign in</button></form></div>"""
    return _ui(body, "Login")


@app.route("/ui/payments/new", methods=["GET", "POST"])
def ui_new_payment():
    message = ""
    if request.method == "POST":
        customer_id = request.form.get("customer_id", "")
        amount = request.form.get("amount", "")
        if not customer_id or not amount:
            message = "<p class='error'>Customer ID and amount are required.</p>"
        else:
            try:
                amount_value = float(amount)
                if amount_value <= 0:
                    raise ValueError
                with app.test_request_context(
                    "/api/payments",
                    method="POST",
                    json={"customer_id": int(customer_id), "amount": amount_value},
                    headers={"X-Api-Key": session.get("api_key", app.config["API_KEY"])},
                ):
                    response = create_payment()
                payload = response[0].get_json()
                if response[1] in (200, 201):
                    message = f"<p class='success'>Payment created: {payload.get('transaction_ref')}</p>"
                else:
                    message = f"<p class='error'>{payload.get('error', 'Payment could not be created.')}</p>"
            except (TypeError, ValueError):
                message = "<p class='error'>Amount must be a positive number and customer ID must be valid.</p>"
    body = f"""<div class="form-card"><p class="eyebrow">Payment operations</p><h2>New payment</h2>
    <p>Create a payment request and receive a transaction reference for tracking.</p>{message}
    <form method="post"><div class="field"><label for="customer-id">Customer ID</label>
    <input id="customer-id" name="customer_id" type="number" min="1" required>
    </div><div class="field"><label for="amount">Amount</label><input id="amount" name="amount" type="number" min="0.01" step="0.01" required>
    </div><button type="submit">Create payment</button></form></div>"""
    return _ui(body, "New Payment")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
