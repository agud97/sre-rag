# Verification And Operations

## Fast Smoke Test

### 1. Verify ArgoCD Apps

Hub:
- `hub-sre-rag`
- `qdrant`
- `holmesgpt`
- `holmesgpt-configs`

Spoke:
- `<spoke>-k8sgpt`
- `<spoke>-k8sgpt-scanner`
- `<spoke>-sre-rag`

Expected:
- `Synced`
- `Healthy`

### 2. Verify Exporter CronJobs

Hub and spoke exporters live in `sre-exporters`.

Expected CronJobs:
- `kubescape-exporter`
- `popeye-exporter`
- `k8sgpt-exporter`

Expected images in the new path:
- Kubescape init: `quay.io/kubescape/kubescape-cli:v3.0.48`
- K8sGPT init: `bitnami/kubectl:latest`
- uploader: `amazon/aws-cli:2.15.40`

### 3. Trigger Manual Jobs

Examples:

```bash
kubectl create job test-ks --from=cronjob/kubescape-exporter -n sre-exporters
kubectl create job test-popeye --from=cronjob/popeye-exporter -n sre-exporters
kubectl create job test-k8sgpt --from=cronjob/k8sgpt-exporter -n sre-exporters
```

Expected:
- jobs complete successfully
- uploader logs show `s3://sre-rag/raw/...`

### 4. Verify S3 Raw Objects

Expected prefixes:
- `raw/kubescape/<cluster_id>/...`
- `raw/popeye/<cluster_id>/...`
- `raw/k8sgpt/<cluster_id>/...`

### 5. Run The Hub Normalizer

```bash
kubectl create job test-norm --from=cronjob/normalizer -n sre-system
kubectl wait --for=condition=complete job/test-norm -n sre-system --timeout=180s
kubectl logs job/test-norm -n sre-system
```

Expected log lines:
- `Loaded ... docs from <cluster_id>`
- `Upserted ... docs to kb_docs_<cluster_id>`
- `Wrote normalized/docs/<cluster_id>/.../docs.jsonl`

### 6. Verify Qdrant

Expected collections:
- `kb_docs_hub`
- `kb_docs_spoke-a`
- additional `kb_docs_<cluster_id>` for every deployed spoke

Payloads should include:
- `cluster_id`
- `tool`
- `source_key`
- `timestamp`

### 7. Verify HolmesGPT

Run inside the Holmes deployment:

```bash
python3 /kb-scripts/kb_tools.py search "k8sgpt" 10 spoke-a
```

Expected:
- search hits with `tool=...`
- `key=raw/.../spoke-a/...`

### 8. Verify The Embedding Model

The embedding service should no longer be a hash-based stub.

Check:

```bash
kubectl get deployment embedding-svc -n sre-system -o yaml
kubectl logs deployment/embedding-svc -n sre-system
kubectl run emb-check --rm -i --restart=Never -n sre-system --image=curlimages/curl \
  --command -- curl -s http://embedding-svc.sre-system.svc:7997/health
```

Expected:
- deployment startup command installs `sentence-transformers`
- logs show model loading
- health endpoint returns `model: intfloat/multilingual-e5-large-instruct`
- `vector_size` is `1024`
- pod is scheduled onto the dedicated `c8-m16384-d120-hp` node class
- service remains healthy while handling `/embed` requests and Kubernetes probes concurrently

## Direct Qdrant Validation

If `kubectl port-forward` is available:

```bash
kubectl port-forward svc/qdrant -n qdrant 6333:6333
```

Then:

```bash
curl -s http://127.0.0.1:6333/collections | jq
curl -s -X POST http://127.0.0.1:6333/collections/kb_docs_spoke-a/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"limit":20,"with_payload":true,"with_vector":false}' | jq
```

## Current Legacy State

Legacy `kb-system` CronJobs are expected to be suspended.

If they are not suspended, the old MinIO path may still be generating data and confusing validation.

Check:

```bash
kubectl get cronjobs -n kb-system
```

Expected:
- `SUSPEND=True` for legacy exporters and legacy normalizer

## Common Failure Modes

### `ImagePullBackOff`

Typical causes:
- wrong image tag
- old ArgoCD revision not yet reconciled

Check:
- app revision
- CronJob image field
- pod events

### Objects Missing In S3

Typical causes:
- exporter job failed
- wrong credentials secret
- wrong `CLUSTER_ID`
- TLS trust issue against S3 endpoint

Check:
- uploader logs
- `S3_VERIFY_SSL`
- object prefix

### Qdrant Missing Data

Typical causes:
- normalizer has not been run since the latest exporter upload
- Qdrant service has no endpoints
- embedding service failed

Check:
- normalizer logs
- Qdrant collection list
- payload scroll output

### HolmesGPT Returns No Results

Typical causes:
- wrong `cluster_id` parameter
- data not indexed yet
- HolmesGPT config drift

Check:
- direct `kb_tools.py search`
- Qdrant payload presence
- `holmesgpt-configs` state
