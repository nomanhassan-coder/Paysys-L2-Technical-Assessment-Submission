# Architecture

## Components

```
┌──────────────┐    HTTP     ┌─────────────────────┐    psycopg2   ┌──────────────────┐
│   Client /   │ ──────────▶ │   Flask API          │ ────────────▶ │  PostgreSQL 15   │
│   Browser    │             │   (Gunicorn workers) │               │  (minipay DB)    │
└──────────────┘             └─────────────────────┘               └──────────────────┘
                                       │
                             ┌─────────▼────────┐
                             │   support_tool    │
                             │   (CLI / L2)      │
                             └──────────────────┘
```

## Kubernetes Layout

```
namespace: minipay
├── Deployment: minipay-api (2 replicas)
│   ├── ConfigMap: minipay-config (non-secret env)
│   ├── Secret: minipay-secrets (DB_PASSWORD, API_KEY)
│   ├── readinessProbe: GET /health :5000
│   ├── livenessProbe: GET /health :5000
│   └── resources: 100m-500m CPU, 128Mi-512Mi RAM
├── StatefulSet: minipay-db (1 replica, PVC 5Gi)
│   └── Service: minipay-db (ClusterIP: None — headless)
├── Service: minipay-api (ClusterIP :80 → :5000)
└── PodDisruptionBudget: minAvailable: 1
```

## Data Model

```
customers ──< transactions ──< callbacks
  id (PK)        id (PK)         id (PK)
  customer_ref   transaction_ref  transaction_id (FK)
  name           customer_id (FK) attempt_no
  created_at     amount           http_status
                 status           callback_status
                 created_at       attempted_at
                 completed_at
                 failure_code
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| ThreadedConnectionPool | Gunicorn workers share pool; avoids per-request connect overhead |
| Parameterised queries everywhere | Prevents SQL injection (INCIDENT-001 root cause) |
| Idempotent payments via `transaction_ref` | Clients can retry on timeout safely |
| Partial index on `status='PROCESSING'` | Only PROCESSING rows need fast lookup; smaller index |
| `StatefulSet` for PostgreSQL | Stable network identity + persistent volume across restarts |
| PodDisruptionBudget | Prevents both API replicas draining simultaneously during node maintenance |
| `X-Api-Key` header auth | Simple, stateless; suitable for service-to-service in internal cluster |
