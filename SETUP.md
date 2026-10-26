# Setup Guide

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | |
| PostgreSQL | 15+ | or Docker image postgres:15-alpine |
| kubectl | 1.28+ | for Kubernetes deployment |
| minikube / k3s | any | local cluster |
| Docker | 24+ | build API image |
| playwright | 1.40+ | UI tests only |

---

## 1. Database

```bash
# Create database
createdb minipay
psql minipay < database/schema.sql
psql minipay < sql/indexes.sql

# Seed the reproducible synthetic dataset
cd database
python generate_data.py > ../seed.sql
psql minipay < ../seed.sql
```

---

## 2. API (local dev)

```bash
cd python
pip install -r requirements.txt

# Environment (or use a .env file with python-dotenv)
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=minipay
export DB_USER=minipay
export DB_PASSWORD=yourpassword
export API_KEY=changeme
export PORT=5000

python app.py
# or: gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Verify: `MINIPAY_API_URL=http://localhost:5000 scripts/health_check.sh`

---

## 3. Kubernetes (Minikube)

```bash
minikube start --memory=4096 --cpus=2

# Build image inside minikube's Docker
eval $(minikube docker-env)
docker build -t minipay-api:latest python/

# Update api-deployment.yaml image to: minipay-api:latest
# and imagePullPolicy: Never (local image)

kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/db-init-configmap.yaml

# Create secret with real values:
kubectl create secret generic minipay-secrets -n minipay \
  --from-literal=DB_PASSWORD=yourpassword \
  --from-literal=API_KEY=changeme

kubectl apply -f kubernetes/db-statefulset.yaml
kubectl apply -f kubernetes/api-deployment.yaml

kubectl rollout status deployment/minipay-api -n minipay

# Port-forward to test
kubectl port-forward svc/minipay-api -n minipay 8080:80
curl http://localhost:8080/health
```

---

## 4. Tests

```bash
# Unit tests (no DB/API needed)
pytest python/test_support_tool.py -v

# API tests (needs running API + DB)
pip install pytest requests
MINIPAY_API_URL=http://localhost:5000 MINIPAY_API_KEY=changeme \
  pytest tests/api/test_api.py -v

# UI tests (needs running API + UI)
pip install pytest-playwright
playwright install chromium
pytest tests/ui/test_ui.py -v --base-url http://localhost:5000
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `minipay` | Database name |
| `DB_USER` | `minipay` | DB user |
| `DB_PASSWORD` | *(required)* | DB password |
| `API_KEY` | `changeme` | Auth key for API |
| `PORT` | `5000` | API listen port |
| `LOG_LEVEL` | `WARNING` | Python log level |
| `MINIPAY_API_URL` | `http://localhost:5000` | Used by support tool + tests |
| `MINIPAY_API_KEY` | `changeme` | Used by support tool + tests |
