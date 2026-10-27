# Kubernetes Live Evidence — MiniPay

**Captured:** 2026-10-27 07:10 (+05:00)  
**Cluster:** Kind `minipay`  
**Kubernetes:** v1.30.0  
**Image:** `minipay-api:latest`, loaded into the Kind node

The submitted manifests were applied without modification:

```bash
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secret.yaml
kubectl apply -f kubernetes/db-init-configmap.yaml
kubectl apply -f kubernetes/db-statefulset.yaml
kubectl apply -f kubernetes/api-deployment.yaml
```

## Cluster and pod status

```text
$ kubectl get nodes -o wide
NAME                    STATUS   ROLES           VERSION   INTERNAL-IP
minipay-control-plane   Ready    control-plane   v1.30.0   172.18.0.2

$ kubectl get pods -n minipay -o wide
NAME                          READY   STATUS    RESTARTS   IP
minipay-api-6757b585b-4mxq8   1/1     Running   0          10.244.0.7
minipay-api-6757b585b-8sgk2   1/1     Running   0          10.244.0.6
minipay-db-0                  1/1     Running   0          10.244.0.8
```

## Services and endpoints

```text
$ kubectl get svc,endpoints -n minipay -o wide
NAME                  TYPE        CLUSTER-IP     PORT(S)
service/minipay-api   ClusterIP   10.96.174.18   80/TCP
service/minipay-db    ClusterIP   None           5432/TCP

NAME          ENDPOINTS
minipay-api   10.244.0.6:5000,10.244.0.7:5000
minipay-db    10.244.0.8:5432
```

## Rollout

```text
$ kubectl rollout status deployment/minipay-api -n minipay
deployment "minipay-api" successfully rolled out

$ kubectl rollout status statefulset/minipay-db -n minipay
partitioned roll out complete: 1 new pods have been updated...
```

The API Deployment reached `2/2` available replicas and the database
StatefulSet reached `1/1` ready replica.

## Health check

The health endpoint was called from inside an API pod through the Kubernetes
service:

```text
$ kubectl exec -n minipay minipay-api-6757b585b-4mxq8 -- \
    python -c "import urllib.request; print(urllib.request.urlopen('http://minipay-api/health').read().decode())"
{"db":"ok","status":"ok"}
```

## Resource configuration and usage

The deployed API pod reported the manifest's resource configuration:

```text
Limits:
  cpu:     500m
  memory:  512Mi
Requests:
  cpu:      100m
  memory:   128Mi
```

`kubectl top pods -n minipay` returned:

```text
error: Metrics API not available
```

This Kind cluster did not include metrics-server, so no CPU or memory usage
numbers are claimed. The configured requests and limits above are real
`kubectl describe pod` output.

## API logs

```text
$ kubectl logs -n minipay deploy/minipay-api --tail=100
[2026-10-27 02:06:35 +0000] [1] [INFO] Starting gunicorn 21.2.0
[2026-10-27 02:06:35 +0000] [1] [INFO] Listening at: http://0.0.0.0:5000 (1)
[2026-10-27 02:06:35 +0000] [1] [INFO] Using worker: sync
[2026-10-27 02:06:35 +0000] [13] [INFO] Booting worker with pid: 13
[2026-10-27 02:06:35 +0000] [14] [INFO] Booting worker with pid: 14
```

During startup, the API readiness probe recorded transient database DNS
failures while PostgreSQL was still initializing:

```text
Health check failed: could not translate host name "minipay-db" to address:
Temporary failure in name resolution
```

After the database became ready, the API service endpoint returned
`{"db":"ok","status":"ok"}` and both API pods remained ready. The transient
startup messages are retained here rather than omitted from the evidence.

## Database logs and events

PostgreSQL initialized `schema.sql` from the mounted ConfigMap and reported
that the database system was ready to accept connections. Kubernetes events
showed successful PVC provisioning, pod scheduling, image pulls, and container
starts. The only warning was the expected transient API readiness failure
during database initialization.

