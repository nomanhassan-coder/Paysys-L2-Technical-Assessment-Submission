# MiniPay — L2 Assessment Submission

**Date:** 2026-10-22  
**Tag:** `submission-v1.0`

---

## Git Branch and Submission Strategy

- `main` contains the working assessment solution and incremental implementation
  commits.
- Feature and investigation work is validated locally before it is merged into
  `main`.
- Each submission is represented by an annotated tag such as `submission-v1.0`
  or `submission-v1.1`.
- A new submission tag is created only after the required tests and evidence
  are updated; earlier tags remain available for comparison and rollback.

---

## Quick Start

```bash
# 1. Prerequisites
docker, kubectl (or minikube), python 3.11+, postgresql 15+

# 2. Database
createdb minipay
psql minipay < database/schema.sql
psql minipay < sql/indexes.sql
python database/generate_data.py > seed.sql
psql minipay < seed.sql

# 3. API (local)
cd python
pip install -r requirements.txt
export DB_HOST=localhost DB_NAME=minipay DB_USER=minipay DB_PASSWORD=yourpass API_KEY=changeme
python app.py

# 4. Kubernetes
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/db-init-configmap.yaml
# Use a secret manager or create a local secret; do not commit real values:
kubectl apply -f kubernetes/secret.yaml
kubectl apply -f kubernetes/db-statefulset.yaml
kubectl apply -f kubernetes/api-deployment.yaml
kubectl rollout status deployment/minipay-api -n minipay

# 5. API tests
pip install pytest requests
MINIPAY_API_URL=http://localhost:5000 MINIPAY_API_KEY=changeme pytest tests/api/ -v

# 6. UI tests
pip install playwright pytest-playwright
playwright install chromium
pytest tests/ui/ -v --base-url http://localhost:5000

# 7. Support tool
python python/support_tool.py --transaction TXN-000001
python python/support_tool.py --stuck --json
python python/support_tool.py --health

# 8. Unit tests
pytest python/test_support_tool.py -v
```

---

## Repository Structure

```
├── README.md
├── SETUP.md
├── ARCHITECTURE.md
├── AI_USAGE.md
├── database/
│   ├── schema.sql
│   └── generate_data.py
├── sql/
│   ├── queries.sql          # 7 required queries
│   ├── indexes.sql          # performance indexes
│   └── PERFORMANCE.md       # before/after EXPLAIN ANALYZE
├── kubernetes/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── api-deployment.yaml  # fixed broken manifest
│   └── db-statefulset.yaml
├── python/
│   ├── app.py               # Flask API
│   ├── support_tool.py      # L2 CLI tool
│   ├── test_support_tool.py # unit tests
│   └── requirements.txt
├── scripts/
│   └── health_check.sh       # reproducible API health check
├── tests/
│   ├── api/
│   │   ├── test_api.py      # pytest API tests
│   │   └── NOTES.md
│   └── ui/
│       └── test_ui.py       # Playwright UI tests
├── investigation/
│   ├── INCIDENT-001-RCA.md
│   ├── INCIDENT-002-RCA.md
│   ├── INCIDENT-003-RCA.md
│   └── kubernetes-findings.md
└── evidence/
    ├── linux.md
    ├── kubernetes-live.md
    └── rancher.md
```
