# INCIDENT-002 RCA — Application Unavailable After Deployment

**Priority:** P1  
**Status:** Resolved  
**Date:** 2026-10-22

---

## Summary

New release deployed to Kubernetes. Pods showed `Running` state but users received connection refused / 502 errors. Root cause: three configuration defects in the Kubernetes manifests.

---

## Observations

```bash
# Pods appear running
kubectl get pods -n minipay
# NAME                           READY   STATUS    RESTARTS   AGE
# minipay-api-6d4f9b8c7-xk2p9   0/1     Running   0          3m
# minipay-api-6d4f9b8c7-mn7r1   0/1     Running   0          3m

# But READY shows 0/1 — readiness probe failing
kubectl describe pod minipay-api-6d4f9b8c7-xk2p9 -n minipay
# Readiness probe failed: Get "http://10.0.0.5:5000/health": connection refused

# Service endpoints empty — no traffic routed
kubectl get endpoints minipay-api -n minipay
# NAME          ENDPOINTS   AGE
# minipay-api   <none>      3m
```

---

## Defects Found in `starter/kubernetes/broken-api.yaml`

### Defect 1 — Service selector mismatch (PRIMARY CAUSE of P1)

```yaml
# broken-api.yaml — Service
spec:
  selector:
    app: minipay-backend      # ← WRONG: no pods have this label
```

```yaml
# broken-api.yaml — Deployment pod template
metadata:
  labels:
    app: minipay-api          # ← actual label
```

**Effect:** Service never routes traffic. `ENDPOINTS` stays `<none>`. All user requests fail.

**Fix:**
```yaml
spec:
  selector:
    app: minipay-api
```

---

### Defect 2 — readinessProbe port mismatch

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 5000      # ← container exposes 5000
```

**Effect:** Pod never becomes Ready. Even if selector were correct, pod excluded from endpoints.

**Fix:**
```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 5000
```

---

### Defect 3 — Service targetPort mismatch

```yaml
# Service ports
ports:
  - port: 80
    targetPort: 5000    # ← container port is 5000
```

**Effect:** Even if selector matched, traffic forwarded to wrong port — connection refused.

**Fix:**
```yaml
ports:
  - port: 80
    targetPort: 5000
```

---

## Corrective Actions

1. Applied all three fixes to manifest (see `kubernetes/api-deployment.yaml`).
2. Re-deployed:
   ```bash
   kubectl apply -f kubernetes/api-deployment.yaml -n minipay
   kubectl rollout status deployment/minipay-api -n minipay
   ```
3. Validated endpoints populated:
   ```bash
   kubectl get endpoints minipay-api -n minipay
   # NAME          ENDPOINTS                         AGE
   # minipay-api   10.244.0.5:5000,10.244.0.6:5000   30s
   ```
4. Health check confirmed:
   ```bash
   curl http://$(kubectl get svc minipay-api -n minipay -o jsonpath='{.spec.clusterIP}')/health
   # {"status":"ok"}
   ```

---

## Preventive Controls

| Control | Description |
|---------|-------------|
| Pre-deploy lint | `kubeval` or `kube-score` catches label/selector mismatches |
| Staging parity | Deploy to staging with same manifests before production |
| Readiness gate | CI gate: wait for `rollout status` before marking deploy success |
| Port convention | Enforce single container port via Helm values/OPA policy |
| GitOps review | Manifest changes require peer review — label/port changes are high-risk |
