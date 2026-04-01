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

Operational note:
- on the current stand, `embedding-svc` is slow enough that the full cron job can lag badly
- if this smoke test stalls, verify fresh `raw/...` first and then use a targeted manual reindex for the newest artifacts instead of waiting for the full backlog

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

Also verify that Holmes chat really exposes KB tools to the LLM:

```bash
kubectl -n holmesgpt exec deploy/holmesgpt-holmes -- /venv/bin/python - <<'PY'
from holmes.config import Config
cfg = Config.load_from_env()
ai = cfg.create_toolcalling_llm(dal=None, model=None)
print("kb_search" in ai.tool_executor.tools_by_name)
print("kb_fetch" in ai.tool_executor.tools_by_name)
PY
```

Expected:
- `True`
- `True`

If either value is `False`, `kb_tools.py` may still work directly while Holmes `/api/chat` remains broken.

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

### 9. Verify Open WebUI Pipe

If the `Holmes SRE Agent` Pipe has been imported into Open WebUI:

- confirm the model selector contains `Holmes SRE Agent`
- open a fresh chat and ask a simple Holmes question
- ask a follow-up question in the same chat and confirm the answer reflects prior context

Minimum expectation:
- Open WebUI shows the Pipe as a model
- the answer is produced by HolmesGPT rather than the default LLM provider
- a follow-up turn still makes sense without repeating the whole previous answer

HTTP/API validation detail:
- the Open WebUI Pipe model id is `holmes_sre_agent.holmes_sre_agent`
- do not test the HTTP API with just `holmes_sre_agent`

Current stand caveat:
- Open WebUI can still fail here if HolmesGPT cannot get a completion from the external LiteLLM endpoint
- this failure mode does not mean S3, Qdrant, or `kb_tools.py` retrieval is broken

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
- Holmes loaded `kb/stack` status but not its tools
- invalid custom tool syntax in the Holmes toolset definition

Check:
- direct `kb_tools.py search`
- Qdrant payload presence
- `holmesgpt-configs` state
- Holmes logs for `Toolset 'kb/stack' is invalid`
- whether `kb_search` / `kb_fetch` are present in `ToolExecutor.tools_by_name`
- live `/etc/holmes/config/custom_toolset.yaml` inside the pod

Important runtime note:
- a valid mounted helper file under `/app/holmes/plugins/toolsets/` does not prove Holmes chat can call the tool
- the effective Holmes chat tool definition must be visible through `/etc/holmes/config/custom_toolset.yaml`
- if `kb/stack` shows `enabled` but `0 tools`, Holmes `/api/chat` will still ignore KB retrieval

### Open WebUI Pipe Fails

Typical causes:
- wrong `HOLMES_API_BASE_URL` valve
- Open WebUI cannot reach the in-cluster Holmes service DNS name
- imported function code is outdated
- HolmesGPT itself is unhealthy
- HolmesGPT chat reaches the external LiteLLM endpoint, but the upstream model returns an error or timeout
- wrong Open WebUI HTTP model id was used

Check:
- the function valves in Open WebUI
- direct curl or browser reachability from the Open WebUI runtime network
- `docs/open-webui-holmes-sre-agent.md`
- direct HolmesGPT `/api/chat` behavior
- the configured LiteLLM endpoint response to `/v1/chat/completions`
- the HTTP request uses `model=holmes_sre_agent.holmes_sre_agent`

## Incident Retrospective: Holmes KB Chat

The Holmes KB path failed in multiple layers on the stand:

1. `kb/stack` first failed validation because its custom toolset definition was missing a top-level `description`.
2. After that, the direct helper script worked, but Holmes chat still did not expose `kb_search` or `kb_fetch`.
3. Runtime introspection showed `kb/stack` was `enabled` with `0 tools`, which meant the chart/runtime was not using the mounted helper YAML as the effective chat tool definition.
4. The real fix was to define `kb/stack` in `applications/hub-holmesgpt.yaml` under Helm `toolsets:` so it was rendered into `/etc/holmes/config/custom_toolset.yaml`.
5. A second runtime validation error then showed Holmes custom YAML tools require `command` as a string or `script`, not a YAML argv list.
6. After converting the tool definitions to Holmes-valid `script` wrappers and restarting the deployment, Holmes `/api/chat` started issuing real `kb_search` calls and Open WebUI returned KB-backed artifact keys.

Separate operational regression:
- `holmesgpt-configs` used to sync an empty `holmesgpt/s3-credentials-normalizer` Secret stub from git
- this broke fresh Holmes pod startup after sync
- the empty stub was removed from git and the namespace-local Secret is now treated as runtime state
