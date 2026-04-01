# Technical Implementation

## High-Level Architecture

The implementation is split into three layers:

1. Spoke and hub exporters
- run in namespace `sre-exporters`
- collect raw findings
- upload raw JSON artifacts to cloud S3 under `raw/<tool>/<cluster_id>/<timestamp>/...`

2. Hub normalization layer
- runs in namespace `sre-system`
- reads all raw artifacts from S3
- turns them into normalized documents
- creates or updates one Qdrant collection per cluster: `kb_docs_<cluster_id>`
- writes normalized snapshots to `normalized/docs/<cluster_id>/<timestamp>/docs.jsonl`

3. HolmesGPT integration
- runs in namespace `holmesgpt`
- uses `kb_tools.py`
- queries Qdrant collections and returns `tool`, `timestamp`, and `source_key`

4. Open WebUI integration
- optional Pipe Function exposes HolmesGPT as a selectable model in the Open WebUI chat interface

5. Multi-spoke delivery model
- each spoke cluster runs its own ArgoCD
- each spoke ArgoCD applies its own local `Application` resources from this repository
- hub ArgoCD is not used as the controller for spoke rollout

## Repository Structure

- `applications/`
  ArgoCD `Application` manifests for hub and spoke rollouts.

- `base/exporters/`
  Shared exporter manifests, namespace, RBAC, and secret stubs.

- `base/hub/`
  Hub-side embedding service, normalizer, and HolmesGPT toolset config.

- `base/k8sgpt-scanner/`
  Shared `k8sgpt` scanner manifest used by the shared spoke app.

- `overlays/hub/`
  Hub-specific `ConfigMap` values for exporters and system components.

- `templates/spoke-exporters/`
  Shared spoke exporter template. Runtime S3 config is shared across all spokes.

- `templates/cluster-identity.yaml`
  Shared cluster identity manifest template. Each spoke applies its own `CLUSTER_ID` locally.

## Exporters

### Kubescape

Files:
- `base/exporters/kubescape/cronjob.yaml`

Behavior:
- init container runs `kubescape`
- uploader container uses `amazon/aws-cli`
- writes to `raw/kubescape/${CLUSTER_ID}/${timestamp}/findings.json`

### Popeye

Files:
- `base/exporters/popeye/cronjob.yaml`

Behavior:
- init container runs `popeye`
- output is extracted to JSON
- uploader container writes to `raw/popeye/${CLUSTER_ID}/${timestamp}/report.json`

### K8sGPT

Files:
- `base/exporters/k8sgpt/cronjob.yaml`
- `base/exporters/k8sgpt/rbac.yaml`
- `base/k8sgpt-scanner/scanner.yaml`

Behavior:
- init container runs `kubectl get results.core.k8sgpt.ai -A -o json`
- uploader container writes to `raw/k8sgpt/${CLUSTER_ID}/${timestamp}/results.json`

## Hub Components

### Embedding Service

Files:
- `base/hub/embedding-svc/embedding-svc.yaml`

Role:
- provides the vector embedding endpoint used by the normalizer and HolmesGPT search

Current model:
- `intfloat/multilingual-e5-large-instruct`
- CPU inference
- 1024-dimensional vectors
- scheduled onto the dedicated `c8-m16384-d120-hp` node class

Runtime detail:
- the service uses `ThreadingHTTPServer` so readiness and liveness probes do not stall behind a long embedding request
- probe timeouts are intentionally higher than the earlier lightweight model

API compatibility:
- current internal clients use `POST /embed` with `{"texts": [...]}`
- the service also exposes `POST /v1/embeddings` in an OpenAI-compatible shape for future integrations

Retrieval detail:
- query embeddings should include an instruction prefix
- document embeddings should not include that prefix
- HolmesGPT query search applies the instruction on the query side before calling the embedding service
- changing model family or vector size requires a clean reindex into fresh Qdrant collections

### Normalizer

Files:
- `base/hub/normalizer/cronjob.yaml`
- `base/hub/normalizer/script-configmap.yaml`

Role:
- scans `raw/` objects in S3
- parses the key shape `raw/<tool>/<cluster_id>/<timestamp>/<filename>`
- creates document payloads
- embeds them
- writes to `kb_docs_<cluster_id>` in Qdrant
- saves normalized snapshots in S3

Important implementation detail:
- `cluster_id` is derived from the S3 object key, not from the hub cluster runtime

Current runtime note:
- the full hourly cron job indexes every raw object under `raw/`
- on the current CPU-only embedding setup this can lag behind fresh uploads
- for recovery or validation, a targeted manual reindex of the latest artifacts per cluster is acceptable and was used on the stand to refresh `hub` and `spoke-a`

### HolmesGPT Toolset

Files:
- `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml`
- `base/hub/holmesgpt-toolset/custom-runbooks-configmap.yaml`
- `base/hub/holmesgpt-toolset/sre-runbooks.yaml`

Role:
- provides `kb_tools.py`
- `search(query, limit, cluster_id)` targets `kb_docs_<cluster_id>`
- if no `cluster_id` is provided, the current default is `kb_docs_hub`

Important implementation detail:
- `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml` is no longer the live source of truth for the Holmes chat toolset definition
- that ConfigMap now carries `kb_tools.py` and `sre-rag-config`
- the live `kb/stack` toolset used by Holmes chat is defined in `applications/hub-holmesgpt.yaml` under Helm `toolsets:`
- Holmes runtime reads the effective custom toolset set from `/etc/holmes/config/custom_toolset.yaml`
- therefore a mounted helper file under `/app/holmes/plugins/toolsets/` is not sufficient by itself to expose `kb_search` and `kb_fetch` to `/api/chat`

Important troubleshooting detail:
- the first failure mode was a missing top-level `description`, which caused `Toolset 'kb/stack' is invalid`
- the second failure mode was subtler: Holmes showed `kb/stack` as `enabled` but with `0 tools`
- this happened because the mounted helper YAML was not the source Holmes used for chat tool loading on this chart/runtime
- a later failure mode came from invalid custom-tool syntax: Holmes YAML tools require `command` as a string or `script`, not a list of argv entries

Current working model:
- `applications/hub-holmesgpt.yaml` defines `kb/stack`, `kb_search`, and `kb_fetch`
- `kb_search` and `kb_fetch` use Holmes `script` wrappers so multi-word query strings survive shell quoting correctly
- `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml` mounts only `/kb-scripts/kb_tools.py`

### Open WebUI Pipe

Files:
- `open-webui/functions/holmes_sre_agent.py`

Role:
- exposes HolmesGPT as an Open WebUI model named `Holmes SRE Agent`
- converts Open WebUI `messages` into HolmesGPT `ask` and `conversation_history`
- calls `POST /api/chat`
- returns an OpenAI-compatible completion response back to Open WebUI

Important implementation detail:
- multi-turn context is preserved by forwarding prior Open WebUI messages as `conversation_history`
- the Pipe itself remains stateless outside the current Open WebUI conversation
- the Pipe itself is healthy if it can execute and reach Holmes; final chat success still depends on the downstream Holmes LLM provider
- for the Open WebUI HTTP API, the effective model id is `holmes_sre_agent.holmes_sre_agent`
- the Open WebUI Pipe can be transport-healthy while Holmes KB tool loading is still broken; validate those layers separately

## ArgoCD Applications

Hub:
- `applications/hub-sre-rag.yaml`
- `applications/hub-qdrant.yaml`
- `applications/hub-holmesgpt.yaml`
- `applications/hub-holmesgpt-configs.yaml`

Spoke:
- `applications/spoke-common-k8sgpt.yaml`
- `applications/spoke-common-k8sgpt-scanner.yaml`
- `applications/spoke-common-sre-rag.yaml`

### ArgoCD Configuration Map

The table below shows where each ArgoCD application reads its desired state from.

| Application | Source type | Config source | What it renders | Runtime config dependencies |
| --- | --- | --- | --- | --- |
| `hub-sre-rag` | Git | `overlays/hub` | hub exporters plus hub services | overlay-local `cluster-config-exporters.yaml` and `cluster-config-system.yaml` |
| `sre-rag` | Git | `templates/spoke-exporters` | spoke exporters | requires local `cluster-identity` ConfigMap plus `s3-credentials` |
| `holmesgpt-configs` | Git | `base/hub/holmesgpt-toolset` | HolmesGPT helper ConfigMaps | provides `kb_tools.py`, runbooks, and `sre-rag-config`; it must not recreate an empty `s3-credentials-normalizer` Secret |
| `holmesgpt` | Helm | chart `holmes` from `https://robusta-charts.storage.googleapis.com`, version `0.19.0` | HolmesGPT deployment | values are embedded in `applications/hub-holmesgpt.yaml`; defines the live `kb/stack` toolset and reads `sre-rag-config`, `s3-credentials-normalizer`, `custom-runbooks`, `sre-runbooks`, and `kb_tools.py` at runtime |
| `qdrant` | Helm | chart `qdrant` from `https://qdrant.github.io/qdrant-helm`, version `0.10.1` | Qdrant StatefulSet and service | values are embedded in `applications/hub-qdrant.yaml` |
| `k8sgpt` | Helm | chart `k8sgpt-operator` from `https://charts.k8sgpt.ai/` | K8sGPT operator | values are embedded in `applications/spoke-common-k8sgpt.yaml` |
| `k8sgpt-scanner` | Git | `base/k8sgpt-scanner` | `K8sGPT` scanner custom resource | depends on the `k8sgpt` operator app already being present |

How the Git-backed apps expand:

- `overlays/hub` includes `base/exporters`, `base/hub`, `cluster-config-exporters.yaml`, and `cluster-config-system.yaml`
- `overlays/hub` also applies `cluster-identity-exporters.yaml` so hub exporters follow the same `cluster-identity` contract as spoke exporters
- `templates/spoke-exporters` includes `base/exporters` and the shared `cluster-config.yaml`
- `templates/cluster-identity.yaml` is applied locally in each spoke cluster before the shared apps
- `base/hub/holmesgpt-toolset` contains HolmesGPT helper ConfigMaps
- `base/k8sgpt-scanner` contains the shared scanner manifest used by spoke apps

Important caveat:

- the shared spoke app names assume one ArgoCD instance per spoke cluster; they are not intended to be applied into a single shared ArgoCD namespace across many clusters
- `overlays/spoke-a` and `overlays/spoke-b` remain in git only as legacy reference and are not the active rollout path

### Per-Spoke ArgoCD Model

The active rollout model is:

- each spoke cluster runs its own ArgoCD
- that local ArgoCD applies the same three shared `applications/spoke-common-*.yaml` manifests
- each spoke cluster applies its own local `cluster-identity` ConfigMap
- the spoke exporter app points to `templates/spoke-exporters`
- the scanner app points to `base/k8sgpt-scanner`

This keeps spoke rollout isolated per cluster and avoids hub-side remote-cluster registration.

## Current Live State

Validated on the stand:
- `hub` acts as both hub and spoke; its exporters also use `sre-exporters/cluster-identity`
- `spoke-a` uses the shared spoke apps and local `cluster-identity`
- raw collection is healthy for both `hub` and `spoke-a`
- fresh targeted normalized snapshots were written for both clusters on `2026-03-31`
- Qdrant contains live collections for both `kb_docs_hub` and `kb_docs_spoke-a`

Known live issues:
- `embedding-svc` is functional but slow enough that full reindex can stall or exceed operational expectations
- Holmes `/api/chat` currently depends on the external LiteLLM endpoint `http://89.111.168.161:32080/v1` with model `minimax-m25`
- if that LiteLLM endpoint or its upstream model returns errors or times out, Open WebUI `Holmes SRE Agent` fails even though direct `kb_tools.py search` still works
- Holmes `prometheus/metrics` remains unhealthy while the VictoriaMetrics backend is broken; this is outside the SRE-RAG KB path

## Incident Notes: Holmes KB Chat Fix

The KB chat path failed in several distinct ways before stabilizing:

1. `kb/stack` first failed validation because the custom toolset definition lacked a top-level `description`.
2. After that, Holmes still did not expose `kb_search` because the mounted helper YAML was not the effective source of truth for `/api/chat`.
3. Once the toolset definition was moved into Helm `toolsets:`, Holmes still rejected the tools because `command` had been defined as a YAML list instead of a Holmes string/script command.
4. After converting the tools to Holmes-valid definitions and restarting the deployment, `kb_search` and `kb_fetch` appeared in `ToolExecutor.tools_by_name`, and Holmes `/api/chat` switched from `kubectl_*` investigation to actual KB retrieval.

Separately, `holmesgpt-configs` had been syncing an empty `holmesgpt/s3-credentials-normalizer` Secret stub from git. That caused fresh Holmes pods to fail startup after sync. The empty stub was removed from git, and the live Secret is now treated as out-of-band runtime state.

## Legacy Cutover State

The old `kb-system` stack used:
- MinIO-backed exporters
- legacy normalizer
- legacy `kb-stack` ArgoCD application from `idp-app-v1`

Current cutover expectation:
- active collection is handled by `sre-exporters` and `sre-system`
- old `kb-system` CronJobs are suspended
- Qdrant is still shared, but the active collections are driven by the new S3-based flow
