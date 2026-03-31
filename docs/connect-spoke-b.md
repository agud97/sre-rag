# Connect `spoke-b`

This guide connects a new `spoke-b` cluster to the current live rollout model.

It assumes:
- hub ArgoCD already runs in the hub cluster
- `hub-spoke-applicationsets` is already installed
- the live multi-spoke model is driven by:
  - `apps/applicationsets/spokes-sre-rag.yaml`
  - `apps/applicationsets/spokes-k8sgpt-scanner.yaml`
  - `clusters/spokes/*.yaml`

## 1. Prepare Access

You need a working kubeconfig for `spoke-b`.

Examples below use:

```bash
export SPOKE_B_KUBECONFIG=/path/to/spoke-b-kubeconfig
export HUB_KUBECONFIG=/root/proj/cross/kubeconfig_6005021
```

Check the target cluster:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl get ns
```

## 2. Register `spoke-b` In Hub ArgoCD

Hub ArgoCD must know the remote cluster under the destination name `spoke-b`.

Create the ArgoCD cluster secret from the `spoke-b` kubeconfig:

```bash
python3 - <<'PY' >/tmp/argocd-cluster-spoke-b.yaml
import json
import os
import yaml

path = os.environ["SPOKE_B_KUBECONFIG"]
with open(path) as f:
    cfg = yaml.safe_load(f)

ctx = cfg["current-context"]
ctxd = next(x["context"] for x in cfg["contexts"] if x["name"] == ctx)
cluster = next(x["cluster"] for x in cfg["clusters"] if x["name"] == ctxd["cluster"])
user = next(x["user"] for x in cfg["users"] if x["name"] == ctxd["user"])

config = {
    "tlsClientConfig": {
        "insecure": False,
        "caData": cluster["certificate-authority-data"],
        "certData": user["client-certificate-data"],
        "keyData": user["client-key-data"],
    }
}

print("apiVersion: v1")
print("kind: Secret")
print("metadata:")
print("  name: cluster-spoke-b")
print("  namespace: argocd")
print("  labels:")
print("    argocd.argoproj.io/secret-type: cluster")
print("stringData:")
print("  name: spoke-b")
print(f"  server: {cluster['server']}")
print("  config: |")
for line in json.dumps(config, separators=(',', ':')).splitlines() or ["{}"]:
    print("    " + line)
PY

KUBECONFIG="$HUB_KUBECONFIG" kubectl apply -f /tmp/argocd-cluster-spoke-b.yaml
```

Validate registration:

```bash
KUBECONFIG="$HUB_KUBECONFIG" \
kubectl -n argocd get secrets -l argocd.argoproj.io/secret-type=cluster
```

## 3. Ensure The `k8sgpt` Operator Exists On `spoke-b`

The scanner `ApplicationSet` only creates the `K8sGPT` custom resource.

The operator itself still follows the separate installation pattern.

If `k8sgpt` is not already installed on `spoke-b`, apply the operator app or install the chart directly in that cluster.

Validation:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n k8sgpt-operator-system get deploy
```

## 4. Create The Exporter Secret On `spoke-b`

The generated `spoke-b-sre-rag` app expects this secret:
- namespace: `sre-exporters`
- name: `s3-credentials`
- keys: `accessKeyId`, `secretAccessKey`

Example:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl create namespace sre-exporters --dry-run=client -o yaml | kubectl apply -f -

KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters create secret generic s3-credentials \
  --from-literal=accessKeyId='REPLACE_ME' \
  --from-literal=secretAccessKey='REPLACE_ME' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 5. Add `spoke-b` To Live Inventory

Create:

`clusters/spokes/spoke-b.yaml`

with:

```yaml
name: spoke-b
cluster_id: spoke-b
argo_cluster: spoke-b
```

Push that change to `main`.

`hub-spoke-applicationsets` should then generate:
- `spoke-b-sre-rag`
- `spoke-b-k8sgpt-scanner`

## 6. Validate In Hub ArgoCD

Check generated applications:

```bash
KUBECONFIG="$HUB_KUBECONFIG" kubectl -n argocd get app spoke-b-sre-rag spoke-b-k8sgpt-scanner
KUBECONFIG="$HUB_KUBECONFIG" kubectl -n argocd get applicationset spokes-sre-rag spokes-k8sgpt-scanner
```

Expected:
- `spoke-b-sre-rag` is `Synced/Healthy`
- `spoke-b-k8sgpt-scanner` is `Synced/Healthy`

## 7. Validate In `spoke-b`

Check exporters:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters get cronjobs
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters get configmap sre-rag-config -o yaml
```

Expected:
- CronJobs `kubescape-exporter`, `popeye-exporter`, `k8sgpt-exporter`
- `CLUSTER_ID: spoke-b`

Check scanner CR:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n k8sgpt-operator-system get k8sgpts.core.k8sgpt.ai
```

Expected:
- `k8sgpt-scanner`

## 8. Trigger A Smoke Test

Run exporter jobs manually:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters create job test-spoke-b-ks --from=cronjob/kubescape-exporter
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters create job test-spoke-b-popeye --from=cronjob/popeye-exporter
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters create job test-spoke-b-k8sgpt --from=cronjob/k8sgpt-exporter
```

Then on hub:

```bash
KUBECONFIG="$HUB_KUBECONFIG" kubectl -n sre-system create job test-norm-spoke-b --from=cronjob/normalizer
```

Then confirm:
- `raw/.../spoke-b/...` objects appear in S3
- `normalized/docs/spoke-b/...` appears in S3
- Qdrant gets `kb_docs_spoke-b`

## Notes

- `spoke-b` should not be added to `clusters/spokes/` before its ArgoCD cluster registration exists in the hub, otherwise `ApplicationSet` validation will fail.
- The current live model still installs the `k8sgpt` operator separately from the generated scanner app.
