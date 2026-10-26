#!/usr/bin/env python3
"""
MiniPay L2 Support Tool
Usage:
  python support_tool.py --transaction TXN000123
  python support_tool.py --transaction TXN000123 --json
  python support_tool.py --stuck
  python support_tool.py --health
"""

import argparse
import json
import logging
import os
import sys
import re
from datetime import datetime, timezone, timedelta

import requests
import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_BASE = os.environ.get("MINIPAY_API_URL", "http://localhost:5000")
API_KEY = os.environ.get("MINIPAY_API_KEY", "changeme")
DB_DSN = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "minipay"),
    "user": os.environ.get("DB_USER", "minipay"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "connect_timeout": 5,
}
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT_SECS", 10))
TXN_REF_PATTERN = re.compile(r"^[A-Z0-9_-]{6,50}$")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("support_tool")

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_NOT_FOUND = 1
EXIT_API_ERROR = 2
EXIT_DB_ERROR = 3
EXIT_VALIDATION_ERROR = 4
EXIT_ANOMALY = 5


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------
def _api_get(path: str) -> dict:
    url = f"{API_BASE}{path}"
    log.debug("GET %s", url)
    try:
        resp = requests.get(
            url,
            headers={"X-Api-Key": API_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        raise RuntimeError(f"API timeout after {REQUEST_TIMEOUT}s: {url}")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Cannot connect to API at {url}")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"API returned {e.response.status_code}: {e.response.text[:200]}")


# ---------------------------------------------------------------------------
# DB client
# ---------------------------------------------------------------------------
def _db_conn():
    try:
        return psycopg2.connect(**DB_DSN, cursor_factory=psycopg2.extras.RealDictCursor)
    except psycopg2.OperationalError as e:
        raise RuntimeError(f"Cannot connect to database: {e}")


def _db_query(sql: str, params=()) -> list[dict]:
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------
STUCK_MINUTES = 15


def detect_anomalies(txn: dict, callbacks: list[dict]) -> list[str]:
    anomalies = []
    now = datetime.now(timezone.utc)

    created = txn.get("created_at")
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    status = txn.get("status", "")

    if status == "PROCESSING" and created:
        age_min = (now - created).total_seconds() / 60
        if age_min > STUCK_MINUTES:
            anomalies.append(f"STUCK: PROCESSING for {age_min:.1f} min (threshold {STUCK_MINUTES} min)")

    if status == "FAILED":
        failure_code = txn.get("failure_code")
        anomalies.append(f"FAILED with code: {failure_code or 'unknown'}")

    if callbacks:
        failed_cbs = [c for c in callbacks if c.get("callback_status") == "FAILED"]
        if len(failed_cbs) == len(callbacks):
            anomalies.append(f"All {len(failed_cbs)} callbacks failed — downstream system may be unreachable")
        elif failed_cbs:
            anomalies.append(f"{len(failed_cbs)}/{len(callbacks)} callbacks failed")

    if not callbacks and status == "SUCCESS":
        anomalies.append("SUCCESS but no callbacks recorded — callback delivery may have failed")

    return anomalies


def recommended_action(txn: dict, anomalies: list[str]) -> str:
    status = txn.get("status", "")
    if "STUCK" in str(anomalies):
        return "Escalate to Tier 3: investigate payment processor; consider manual status update after confirmation"
    if status == "FAILED":
        return "Review failure_code; advise customer to retry; check processor logs for root cause"
    if "callback" in str(anomalies).lower():
        return "Check callback URL reachability; retry callback delivery; notify integration team"
    if status == "SUCCESS":
        return "Transaction healthy. No action required."
    return "Monitor; escalate if status does not change within 5 minutes"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_transaction(ref: str, as_json: bool) -> int:
    if not TXN_REF_PATTERN.match(ref):
        _output({"error": f"Invalid transaction reference format: {ref}"}, as_json)
        return EXIT_VALIDATION_ERROR

    # Fetch from API
    try:
        txn = _api_get(f"/api/payments/{ref}")
    except RuntimeError as e:
        if e.args and str(e).startswith("API returned 404:"):
            _output({"error": f"Transaction not found: {ref}"}, as_json)
            return EXIT_NOT_FOUND
        log.error("API error: %s", e)
        _output({"error": str(e)}, as_json)
        return EXIT_API_ERROR

    if not txn or txn.get("error"):
        _output({"error": f"Transaction not found: {ref}"}, as_json)
        return EXIT_NOT_FOUND

    # Fetch callbacks from DB
    callbacks = []
    try:
        callbacks = _db_query(
            "SELECT * FROM callbacks WHERE transaction_id = %s ORDER BY attempt_no",
            (txn["id"],),
        )
    except RuntimeError as e:
        log.warning("DB unavailable for callbacks: %s", e)

    anomalies = detect_anomalies(txn, callbacks)
    action = recommended_action(txn, anomalies)

    report = {
        "transaction": {
            "id": txn.get("id"),
            "ref": txn.get("transaction_ref"),
            "customer_id": txn.get("customer_id"),
            "amount": str(txn.get("amount")),
            "status": txn.get("status"),
            "created_at": txn.get("created_at"),
            "completed_at": txn.get("completed_at"),
            "failure_code": txn.get("failure_code"),
        },
        "callbacks": [
            {
                "attempt": c.get("attempt_no"),
                "status": c.get("callback_status"),
                "http_status": c.get("http_status"),
                "attempted_at": str(c.get("attempted_at")),
            }
            for c in callbacks
        ],
        "anomalies": anomalies,
        "recommended_action": action,
    }

    _output(report, as_json)
    return EXIT_ANOMALY if anomalies else EXIT_OK


def cmd_stuck(as_json: bool) -> int:
    try:
        rows = _db_query(
            """SELECT transaction_ref, customer_id, amount, created_at,
                      EXTRACT(EPOCH FROM (NOW() - created_at))/60 AS minutes_stuck
               FROM transactions
               WHERE status = 'PROCESSING'
                 AND created_at < NOW() - INTERVAL '15 minutes'
               ORDER BY created_at ASC
               LIMIT 50""",
        )
    except RuntimeError as e:
        _output({"error": str(e)}, as_json)
        return EXIT_DB_ERROR

    result = {"stuck_count": len(rows), "transactions": [dict(r) for r in rows]}
    _output(result, as_json)
    return EXIT_OK if not rows else EXIT_ANOMALY


def cmd_health(as_json: bool) -> int:
    results = {}
    exit_code = EXIT_OK

    # API
    try:
        data = _api_get("/health")
        results["api"] = {"status": "ok", "response": data}
    except RuntimeError as e:
        results["api"] = {"status": "error", "error": str(e)}
        exit_code = EXIT_API_ERROR

    # DB
    try:
        _db_query("SELECT 1")
        results["db"] = {"status": "ok"}
    except RuntimeError as e:
        results["db"] = {"status": "error", "error": str(e)}
        exit_code = EXIT_DB_ERROR

    _output(results, as_json)
    return exit_code


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _output(data: dict, as_json: bool):
    if as_json:
        print(json.dumps(data, default=str, indent=2))
    else:
        _pretty(data)


def _pretty(data: dict, indent: int = 0):
    prefix = "  " * indent
    for k, v in data.items():
        if isinstance(v, dict):
            print(f"{prefix}{k}:")
            _pretty(v, indent + 1)
        elif isinstance(v, list):
            print(f"{prefix}{k}: ({len(v)} items)")
            for item in v:
                if isinstance(item, dict):
                    _pretty(item, indent + 1)
                    print()
                else:
                    print(f"{prefix}  - {item}")
        else:
            print(f"{prefix}{k}: {v}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="MiniPay L2 Support Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--transaction", "-t", metavar="REF", help="Diagnose a transaction by reference")
    parser.add_argument("--stuck", action="store_true", help="List stuck PROCESSING transactions")
    parser.add_argument("--health", action="store_true", help="Health check API and database")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Machine-readable JSON output")
    args = parser.parse_args()

    if args.transaction:
        sys.exit(cmd_transaction(args.transaction, args.as_json))
    elif args.stuck:
        sys.exit(cmd_stuck(args.as_json))
    elif args.health:
        sys.exit(cmd_health(args.as_json))
    else:
        parser.print_help()
        sys.exit(EXIT_VALIDATION_ERROR)


if __name__ == "__main__":
    main()
