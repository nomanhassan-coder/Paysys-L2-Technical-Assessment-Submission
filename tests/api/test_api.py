"""
API tests for MiniPay — pytest + requests
Requires running API at $MINIPAY_API_URL (default http://localhost:5000)
Run: pytest tests/api/test_api.py -v

Uses a test API key configured in the app.
"""

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("MINIPAY_API_URL", "http://localhost:5000")
API_KEY = os.environ.get("MINIPAY_API_KEY", "changeme")
RESPONSE_TIME_THRESHOLD_MS = 500

HEADERS = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def url(path: str) -> str:
    return f"{BASE_URL}{path}"


def unique_ref(prefix: str = "TST") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def customer():
    """Create one customer for the test session."""
    resp = requests.post(
        url("/api/customers"),
        json={"name": "Test Customer", "customer_ref": unique_ref("CUST")},
        headers=HEADERS,
        timeout=10,
    )
    assert resp.status_code == 201, f"Setup failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_ok(self):
        start = time.time()
        resp = requests.get(url("/health"), timeout=10)
        elapsed_ms = (time.time() - start) * 1000
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert elapsed_ms < RESPONSE_TIME_THRESHOLD_MS, f"Health too slow: {elapsed_ms:.0f}ms"

    def test_health_response_time(self):
        start = time.time()
        requests.get(url("/health"), timeout=10)
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < RESPONSE_TIME_THRESHOLD_MS


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class TestAuth:
    def test_no_api_key_returns_401(self):
        resp = requests.get(url("/api/customers/1"), timeout=10)
        assert resp.status_code == 401

    def test_wrong_api_key_returns_401(self):
        resp = requests.get(
            url("/api/customers/1"),
            headers={"X-Api-Key": "wrong"},
            timeout=10,
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
class TestCustomers:
    def test_create_customer_success(self):
        resp = requests.post(
            url("/api/customers"),
            json={"name": "Alice Test", "customer_ref": unique_ref("CUST")},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Alice Test"
        assert "id" in data
        assert "created_at" in data

    def test_create_customer_missing_name(self):
        resp = requests.post(
            url("/api/customers"),
            json={"customer_ref": unique_ref("CUST")},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_create_duplicate_customer_ref(self, customer):
        resp = requests.post(
            url("/api/customers"),
            json={"name": "Duplicate", "customer_ref": customer["customer_ref"]},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 409

    def test_get_customer_not_found(self):
        resp = requests.get(url("/api/customers/999999"), headers=HEADERS, timeout=10)
        assert resp.status_code == 404

    def test_get_customer_success(self, customer):
        resp = requests.get(url(f"/api/customers/{customer['id']}"), headers=HEADERS, timeout=10)
        assert resp.status_code == 200
        assert resp.json()["id"] == customer["id"]


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
class TestPayments:
    def test_create_payment_success(self, customer):
        ref = unique_ref("TXN")
        resp = requests.post(
            url("/api/payments"),
            json={"customer_id": customer["id"], "amount": 99.99, "transaction_ref": ref},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["transaction_ref"] == ref
        assert data["status"] == "PROCESSING"
        assert data["amount"] == "99.99" or float(data["amount"]) == 99.99

    def test_create_payment_idempotent(self, customer):
        ref = unique_ref("TXN")
        first = requests.post(
            url("/api/payments"),
            json={"customer_id": customer["id"], "amount": 50.00, "transaction_ref": ref},
            headers=HEADERS,
            timeout=10,
        )
        assert first.status_code == 201
        second = requests.post(
            url("/api/payments"),
            json={"customer_id": customer["id"], "amount": 50.00, "transaction_ref": ref},
            headers=HEADERS,
            timeout=10,
        )
        # Idempotent: returns existing
        assert second.status_code == 200
        assert second.json()["transaction_ref"] == ref

    def test_create_payment_missing_amount(self, customer):
        resp = requests.post(
            url("/api/payments"),
            json={"customer_id": customer["id"]},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 400
        assert "amount" in resp.json().get("fields", {})

    def test_create_payment_negative_amount(self, customer):
        resp = requests.post(
            url("/api/payments"),
            json={"customer_id": customer["id"], "amount": -10},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 400

    def test_create_payment_missing_customer(self):
        resp = requests.post(
            url("/api/payments"),
            json={"customer_id": 999999, "amount": 10.00},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code in (400, 404)

    def test_get_payment_success(self, customer):
        ref = unique_ref("TXN")
        requests.post(
            url("/api/payments"),
            json={"customer_id": customer["id"], "amount": 25.00, "transaction_ref": ref},
            headers=HEADERS,
            timeout=10,
        )
        resp = requests.get(url(f"/api/payments/{ref}"), headers=HEADERS, timeout=10)
        assert resp.status_code == 200
        assert resp.json()["transaction_ref"] == ref

    def test_get_payment_not_found(self):
        resp = requests.get(url("/api/payments/TXN-NOTEXIST999"), headers=HEADERS, timeout=10)
        assert resp.status_code == 404

    def test_get_payment_invalid_ref_format(self):
        resp = requests.get(url("/api/payments/bad ref!"), headers=HEADERS, timeout=10)
        assert resp.status_code in (400, 404)

    def test_list_customer_payments(self, customer):
        resp = requests.get(
            url(f"/api/customers/{customer['id']}/payments"),
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_payments_unknown_customer(self):
        resp = requests.get(url("/api/customers/999999/payments"), headers=HEADERS, timeout=10)
        assert resp.status_code == 404

    def test_payment_response_time(self, customer):
        ref = unique_ref("TXN")
        requests.post(
            url("/api/payments"),
            json={"customer_id": customer["id"], "amount": 1.00, "transaction_ref": ref},
            headers=HEADERS,
            timeout=10,
        )
        start = time.time()
        requests.get(url(f"/api/payments/{ref}"), headers=HEADERS, timeout=10)
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < RESPONSE_TIME_THRESHOLD_MS, f"GET payment too slow: {elapsed_ms:.0f}ms"
