"""Unit tests for support_tool.py — anomaly detection + validation logic."""

import pytest
from datetime import datetime, timezone, timedelta

# Import testable units (no DB/API calls)
from support_tool import (
    detect_anomalies,
    recommended_action,
    TXN_REF_PATTERN,
    STUCK_MINUTES,
)


# ---------------------------------------------------------------------------
# TXN_REF_PATTERN
# ---------------------------------------------------------------------------
class TestTxnRefPattern:
    def test_valid_simple(self):
        assert TXN_REF_PATTERN.match("TXN001")

    def test_valid_with_hyphen(self):
        assert TXN_REF_PATTERN.match("TXN-000123")

    def test_valid_with_underscore(self):
        assert TXN_REF_PATTERN.match("TXN_ABC_123")

    def test_too_short(self):
        assert not TXN_REF_PATTERN.match("TXN")

    def test_lowercase_rejected(self):
        assert not TXN_REF_PATTERN.match("txn001")

    def test_apostrophe_rejected(self):
        assert not TXN_REF_PATTERN.match("TXN'001")

    def test_space_rejected(self):
        assert not TXN_REF_PATTERN.match("TXN 001")

    def test_too_long(self):
        assert not TXN_REF_PATTERN.match("T" * 51)

    def test_exactly_50_chars_valid(self):
        assert TXN_REF_PATTERN.match("T" * 50)


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------
class TestDetectAnomalies:
    def _txn(self, status="SUCCESS", created_offset_min=0, failure_code=None):
        created = datetime.now(timezone.utc) - timedelta(minutes=created_offset_min)
        return {
            "id": 1,
            "transaction_ref": "TXN000001",
            "status": status,
            "created_at": created.isoformat(),
            "completed_at": None,
            "failure_code": failure_code,
            "amount": "100.00",
        }

    def test_success_no_anomalies(self):
        txn = self._txn(status="SUCCESS")
        callbacks = [{"callback_status": "SUCCESS", "attempt_no": 1}]
        assert detect_anomalies(txn, callbacks) == []

    def test_stuck_processing(self):
        txn = self._txn(status="PROCESSING", created_offset_min=STUCK_MINUTES + 5)
        anomalies = detect_anomalies(txn, [])
        assert any("STUCK" in a for a in anomalies)

    def test_processing_not_yet_stuck(self):
        txn = self._txn(status="PROCESSING", created_offset_min=STUCK_MINUTES - 1)
        anomalies = detect_anomalies(txn, [])
        assert not any("STUCK" in a for a in anomalies)

    def test_failed_status(self):
        txn = self._txn(status="FAILED", failure_code="INSUFFICIENT_FUNDS")
        anomalies = detect_anomalies(txn, [])
        assert any("FAILED" in a for a in anomalies)
        assert any("INSUFFICIENT_FUNDS" in a for a in anomalies)

    def test_all_callbacks_failed(self):
        txn = self._txn(status="SUCCESS")
        callbacks = [
            {"callback_status": "FAILED", "attempt_no": 1},
            {"callback_status": "FAILED", "attempt_no": 2},
        ]
        anomalies = detect_anomalies(txn, callbacks)
        assert any("all" in a.lower() or "All" in a for a in anomalies)

    def test_partial_callback_failure(self):
        txn = self._txn(status="SUCCESS")
        callbacks = [
            {"callback_status": "SUCCESS", "attempt_no": 1},
            {"callback_status": "FAILED", "attempt_no": 2},
        ]
        anomalies = detect_anomalies(txn, callbacks)
        assert any("1/2" in a for a in anomalies)

    def test_success_no_callbacks(self):
        txn = self._txn(status="SUCCESS")
        anomalies = detect_anomalies(txn, [])
        assert any("no callbacks" in a.lower() for a in anomalies)

    def test_processing_no_callbacks_not_stuck(self):
        # PROCESSING without callbacks and not yet stuck — no anomaly expected
        txn = self._txn(status="PROCESSING", created_offset_min=1)
        anomalies = detect_anomalies(txn, [])
        assert anomalies == []

    def test_processing_naive_timestamp(self):
        txn = self._txn(status="PROCESSING", created_offset_min=STUCK_MINUTES + 1)
        txn["created_at"] = txn["created_at"].replace("+00:00", "")
        anomalies = detect_anomalies(txn, [])
        assert any("STUCK" in a for a in anomalies)


# ---------------------------------------------------------------------------
# recommended_action
# ---------------------------------------------------------------------------
class TestRecommendedAction:
    def test_stuck_escalate(self):
        txn = {"status": "PROCESSING"}
        action = recommended_action(txn, ["STUCK: PROCESSING for 20.0 min (threshold 15 min)"])
        assert "Escalate" in action or "escalate" in action

    def test_failed_retry(self):
        txn = {"status": "FAILED"}
        action = recommended_action(txn, ["FAILED with code: TIMEOUT"])
        assert "retry" in action.lower() or "failure_code" in action.lower()

    def test_healthy_no_action(self):
        txn = {"status": "SUCCESS"}
        action = recommended_action(txn, [])
        assert "No action" in action or "healthy" in action.lower()

    def test_callback_failure(self):
        txn = {"status": "SUCCESS"}
        action = recommended_action(txn, ["All 2 callbacks failed"])
        assert "callback" in action.lower()
