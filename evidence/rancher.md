# Rancher Evidence — MiniPay Cluster Operations

## Attempt status

**Attempt date:** 2026-10-27
**Result:** Blocked by the local environment; no Rancher or Kubernetes cluster
was available.

The following checks were run from the final submission workspace:

```text
$ command -v rancher
# no output: Rancher CLI is not installed

$ command -v kubectl
# no output: kubectl is not installed

$ command -v minikube
# no output

$ command -v kind
# no output

$ curl -k -sS -m 3 -o /tmp/rancher-response -w 'HTTP %{http_code}\n' https://localhost/v3
curl: (7) Failed to connect to localhost port 443 after 0 ms: Could not connect to server
HTTP 000

$ curl -k -sS -m 3 -o /tmp/rancher-response -w 'HTTP %{http_code}\n' https://localhost:8443/v3
curl: (7) Failed to connect to localhost port 8443 after 0 ms: Could not connect to server
HTTP 000

$ curl -sS -m 3 -o /tmp/rancher-response -w 'HTTP %{http_code}\n' http://localhost:8080/v3
curl: (7) Failed to connect to localhost port 8080 after 0 ms: Could not connect to server
HTTP 000

$ docker ps --format '{{.Names}} {{.Image}} {{.Ports}}'
minipay-postgres postgres:15-alpine 0.0.0.0:55432->5432/tcp
```

Therefore this submission does **not** claim a Rancher deployment, pod
readiness, rollout, or Rancher UI screenshot. The blocker is environmental:
there is no Rancher endpoint, Kubernetes client, or local Kubernetes
distribution available in this workspace. The PostgreSQL Docker container is
not a Kubernetes cluster and cannot produce Rancher evidence.

## Reproducible Rancher deployment procedure

The following procedure is what should be run on a Rancher-managed Kubernetes
cluster. It uses the manifests committed in [`kubernetes/`](../kubernetes/).
Replace placeholder secret values through Rancher or a secret manager; do not
commit real credentials.

### 1. Connect to the Rancher cluster

In Rancher, open **Cluster Explorer → Kubernetes → Download KubeConfig**.
Export the downloaded configuration:

```bash
export KUBECONFIG=/path/to/rancher-kubeconfig.yaml
kubectl cluster-info
kubectl get nodes -o wide
```

### 2. Build and publish the API image

Build [`python/Dockerfile`](../python/Dockerfile), push it to a registry
accessible by the cluster, and update the image in
`kubernetes/api-deployment.yaml`:

```bash
docker build -t REGISTRY/minipay-api:submission-v1.1 python/
docker push REGISTRY/minipay-api:submission-v1.1
```

The cluster nodes must be able to pull this image. `minipay-api:latest` is
usable only when the image is already loaded into the target cluster runtime.

### 3. Create namespace and configuration

```bash
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl -n minipay create secret generic minipay-secrets \
  --from-literal=DB_PASSWORD='REPLACE_WITH_REAL_PASSWORD' \
  --from-literal=API_KEY='REPLACE_WITH_REAL_API_KEY' \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f kubernetes/db-init-configmap.yaml
```

### 4. Deploy PostgreSQL and API

```bash
kubectl apply -f kubernetes/db-statefulset.yaml
kubectl -n minipay rollout status statefulset/minipay-db --timeout=180s
kubectl apply -f kubernetes/api-deployment.yaml
kubectl -n minipay rollout status deployment/minipay-api --timeout=180s
```

### 5. Capture Rancher/Kubernetes evidence

Run these commands and save their real output alongside Rancher screenshots:

```bash
kubectl get nodes -o wide
kubectl get all -n minipay
kubectl get pods -n minipay -o wide
kubectl get svc,endpoints -n minipay
kubectl describe deployment minipay-api -n minipay
kubectl logs -n minipay deploy/minipay-api --tail=100
kubectl get events -n minipay --sort-by='.lastTimestamp'
kubectl top pods -n minipay
```

In Rancher, capture **Cluster Explorer → Workloads → Deployments**,
**Workloads → Pods**, the API pod logs, and the deployment resource/health
view. Redact tokens, passwords, and private registry credentials.

### 6. Verify the service

Use port-forwarding if the service has no external load balancer:

```bash
kubectl -n minipay port-forward svc/minipay-api 5000:5000
curl -fsS http://localhost:5000/health
```

Expected response:

```json
{"db":"ok","status":"ok"}
```

## Scaling and rollback commands

```bash
kubectl scale deployment minipay-api -n minipay --replicas=4
kubectl rollout status deployment/minipay-api -n minipay
kubectl rollout restart deployment/minipay-api -n minipay
kubectl rollout undo deployment/minipay-api -n minipay
```
