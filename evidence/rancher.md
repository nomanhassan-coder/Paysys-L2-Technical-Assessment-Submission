# Rancher Evidence — MiniPay Cluster Operations

> **Evidence status:** The commands below are the reproducible capture procedure. No Rancher cluster output is claimed unless it is captured during deployment.

---

## Cluster / Workload Visibility

```bash
# Cluster summary
kubectl get nodes -o wide

# All workloads in minipay namespace
kubectl get all -n minipay
```

Review the captured output for readiness after applying the manifests. In Rancher UI, use **Cluster Explorer → Workloads → Deployments** for the same view.

---

## Pod Status and Logs

```bash
# Pod status
kubectl get pods -n minipay -o wide

# Logs for API pods
kubectl logs -n minipay deploy/minipay-api --tail=100 --follow

# Logs from previous crashed container (if restart occurred)
kubectl logs -n minipay <pod-name> --previous
```

In Rancher: **Workloads → Pods → minipay-api → ... → View Logs**

---

## Configuration / Environment Inspection

```bash
# View ConfigMap
kubectl describe configmap minipay-config -n minipay

# Verify Secret keys exist (not values)
kubectl get secret minipay-secrets -n minipay -o jsonpath='{.data}' | python3 -c "import sys,json; [print(k) for k in json.load(sys.stdin)]"

# Describe pod to see resolved env
kubectl describe pod <pod-name> -n minipay | grep -A5 "Environment:"
```

In Rancher: **Config → ConfigMaps** and **Config → Secrets** (values redacted in UI).

---

## Scaling and Rollout / Restart

```bash
# Scale up
kubectl scale deployment minipay-api -n minipay --replicas=4

# Rolling restart (picks up new image / config)
kubectl rollout restart deployment/minipay-api -n minipay

# Watch rollout
kubectl rollout status deployment/minipay-api -n minipay

# Rollback to previous version
kubectl rollout undo deployment/minipay-api -n minipay
```

In Rancher: **Workloads → Deployments → minipay-api → ... → Redeploy / Edit → change replica count → Save**

---

## Basic Resource / Health Visibility

```bash
# Resource usage (requires metrics-server)
kubectl top pods -n minipay
# Output depends on the target cluster and metrics-server availability.

# Events (recent warnings/errors)
kubectl get events -n minipay --sort-by='.lastTimestamp' | tail -20
```

In Rancher: **Cluster → Monitoring** (if Prometheus/Grafana installed via Rancher Apps) shows CPU/memory graphs per pod.
