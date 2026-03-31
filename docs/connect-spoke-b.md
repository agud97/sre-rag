# Connect `spoke-b` With Local ArgoCD

This guide connects `spoke-b` using the active per-spoke ArgoCD model.

In this model:
- `spoke-b` runs its own ArgoCD
- the spoke cluster applies its own local `Application` resources
- hub ArgoCD is not used to manage `spoke-b`

## 1. Create `cluster-identity`

Apply a local cluster identity manifest in `spoke-b`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-identity
  namespace: sre-exporters
data:
  CLUSTER_ID: "spoke-b"
```

The repository contains a reusable template at `templates/cluster-identity.yaml`.

## 2. Prepare The Spoke ArgoCD Apps

The repository already contains the shared application manifests needed for every spoke:

- `applications/spoke-common-k8sgpt.yaml`
- `applications/spoke-common-k8sgpt-scanner.yaml`
- `applications/spoke-common-sre-rag.yaml`

These should be applied in the `spoke-b` cluster's own ArgoCD namespace.

## 3. Create The Exporter Secret In `spoke-b`

The exporters expect:
- namespace: `sre-exporters`
- secret: `s3-credentials`
- keys: `accessKeyId`, `secretAccessKey`

Example:

```bash
export SPOKE_B_KUBECONFIG=/path/to/spoke-b-kubeconfig

KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl create namespace sre-exporters --dry-run=client -o yaml | kubectl apply -f -

sed 's/REPLACE_ME/spoke-b/' templates/cluster-identity.yaml | \
  KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl apply -f -

KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters create secret generic s3-credentials \
  --from-literal=accessKeyId='REPLACE_ME' \
  --from-literal=secretAccessKey='REPLACE_ME' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 4. Apply The ArgoCD Applications In `spoke-b`

Apply them in this order:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl apply -f applications/spoke-common-k8sgpt.yaml
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl apply -f applications/spoke-common-k8sgpt-scanner.yaml
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl apply -f applications/spoke-common-sre-rag.yaml
```

## 5. Validate In `spoke-b` ArgoCD

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n argocd get applications.argoproj.io
```

Expected:
- `k8sgpt`
- `k8sgpt-scanner`
- `sre-rag`

All should converge to `Synced`, and the two spoke apps should become `Healthy`.

## 6. Validate Runtime Resources In `spoke-b`

Check exporters:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters get cronjobs
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters get configmap cluster-identity -o yaml
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters get configmap sre-rag-config -o yaml
```

Expected:
- `kubescape-exporter`
- `popeye-exporter`
- `k8sgpt-exporter`
- `CLUSTER_ID: spoke-b` in `cluster-identity`

Check scanner:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n k8sgpt-operator-system get k8sgpts.core.k8sgpt.ai
```

Expected:
- `k8sgpt-scanner`

## 7. Run A Smoke Test

Trigger exporter jobs:

```bash
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters create job test-spoke-b-ks --from=cronjob/kubescape-exporter
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters create job test-spoke-b-popeye --from=cronjob/popeye-exporter
KUBECONFIG="$SPOKE_B_KUBECONFIG" kubectl -n sre-exporters create job test-spoke-b-k8sgpt --from=cronjob/k8sgpt-exporter
```

Then on hub:

```bash
export HUB_KUBECONFIG=/root/proj/cross/kubeconfig_6005021
KUBECONFIG="$HUB_KUBECONFIG" kubectl -n sre-system create job test-norm-spoke-b --from=cronjob/normalizer
```

Then confirm:
- `raw/.../spoke-b/...` appears in S3
- `normalized/docs/spoke-b/...` appears in S3
- Qdrant gets `kb_docs_spoke-b`
