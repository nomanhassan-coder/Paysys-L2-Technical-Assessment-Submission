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
<style>body{font-family:sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem}
nav a{margin-right:1rem}.error{color:#a00}.success{color:#176b2c}
label{display:block;margin:.75rem 0}input{display:block;padding:.45rem;width:100%;max-width:24rem}
button{padding:.5rem 1rem}</style></head>
<body><header><h1>MiniPay</h1><nav><a href="/ui">Search</a>
<a href="/ui/payments/new">New payment</a><a href="/ui/login">Login</a></nav></header>
<main>{{ body|safe }}</main></body></html>"""


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
    body = f"""<h2>Find a transaction</h2>
    <form method="get"><label for="transaction-ref">Transaction ref</label>
    <input id="transaction-ref" name="transaction_ref" placeholder="Transaction ref" required>
    <button type="submit">Search</button></form>{result}"""
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
    body = f"""<h2>Sign in</h2>{message}
    <form method="post"><label for="api-key">API key</label>
    <input id="api-key" name="api_key" type="password" aria-label="API key" required>
    <button type="submit">Sign in</button></form>"""
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
    body = f"""<h2>New payment</h2>{message}
    <form method="post"><label for="customer-id">Customer ID</label>
    <input id="customer-id" name="customer_id" type="number" min="1" required>
    <label for="amount">Amount</label><input id="amount" name="amount" type="number" min="0.01" step="0.01" required>
    <button type="submit">Create payment</button></form>"""
    return _ui(body, "New Payment")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
