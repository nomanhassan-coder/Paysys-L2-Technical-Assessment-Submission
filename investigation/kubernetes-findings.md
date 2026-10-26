# Kubernetes Manifest Findings — broken-api.yaml

**File:** `starter/kubernetes/broken-api.yaml`

Three defects found. Each independently prevents service from routing traffic.

---

## Defect 1 — Service selector does not match pod labels (CRITICAL)

| | Value |
|-|-------|
| **Service selector** | `app: minipay-backend` |
| **Pod label** | `app: minipay-api` |

No pods match the Service selector → `ENDPOINTS` list stays empty → all user traffic fails with 502/connection refused.

```yaml
# broken
selector:
  app: minipay-backend

# fixed
selector:
  app: minipay-api
```

---

## Defect 2 — readinessProbe targets wrong port

| | Value |
|-|-------|
| **Container port** | `5000` |
| **readinessProbe port** | `8081` |
| **livenessProbe port** | `5000` (correct) |

Readiness probe connects to 8081 (nothing listening) → probe fails → pod stays `0/1 Ready` → never added to endpoints even if selector were fixed.

```yaml
# broken
readinessProbe:
  httpGet:
    port: 8081

# fixed
readinessProbe:
  httpGet:
    port: 5000
```

---

## Defect 3 — Service targetPort does not match container port

| | Value |
|-|-------|
| **Container port** | `5000` |
| **Service targetPort** | `8081` |

Traffic forwarded to port 8081 inside pod → nothing listening → connection refused at pod level.

```yaml
# broken
ports:
  - port: 80
    targetPort: 8081

# fixed
ports:
  - port: 80
    targetPort: 5000
```

---

## Additional Missing Production Controls

These are not bugs in the file but gaps for a production system:

| Gap | Recommendation |
|-----|---------------|
| No resource requests/limits | Add `resources.requests` and `resources.limits` to prevent noisy-neighbour issues |
| No `Secrets` for DB credentials | Use K8s Secret + `secretKeyRef`, never plaintext env vars |
| No `ConfigMap` | Externalise non-secret config |
| No `PodDisruptionBudget` | Add PDB to maintain availability during node drain |
| `namespace: minipay` referenced but not created | Add `Namespace` manifest or `kubectl create namespace minipay` in setup |
| Image `YOUR_IMAGE_HERE` | Must be replaced with real registry image before deploy |
