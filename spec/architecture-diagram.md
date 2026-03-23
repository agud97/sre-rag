# Architecture Diagram

## End-To-End Flow

```text
                    +----------------------+
                    |   Spoke Cluster A    |
                    |  namespace:          |
                    |  sre-exporters       |
                    +----------+-----------+
                               |
                               | raw/kubescape/spoke-a/<ts>/...
                               | raw/popeye/spoke-a/<ts>/...
                               | raw/k8sgpt/spoke-a/<ts>/...
                               v
                      +-------------------+
                      |   Cloud S3 Bucket |
                      |   sre-rag         |
                      |                   |
                      | raw/...           |
                      | normalized/docs/  |
                      +---------+---------+
                                ^
                                |
                                | raw/kubescape/hub/<ts>/...
                                | raw/popeye/hub/<ts>/...
                                | raw/k8sgpt/hub/<ts>/...
                    +-----------+----------+
                    |     Hub Cluster      |
                    |  namespace:          |
                    |  sre-exporters       |
                    +-----------+----------+
                                |
                                | reads raw/*
                                | writes normalized/docs/*
                                v
                    +----------------------+
                    |   Hub Normalizer     |
                    | namespace: sre-system|
                    +-----------+----------+
                                |
                                | embeddings
                                v
                    +----------------------+
                    |   Embedding Service  |
                    | namespace: sre-system|
                    +----------------------+
                                |
                                | upsert points with payload:
                                | cluster_id, tool, source_key
                                v
                    +----------------------+
                    |       Qdrant         |
                    | collections:         |
                    | kb_docs_hub          |
                    | kb_docs_spoke-a      |
                    +-----------+----------+
                                |
                                | search(cluster_id)
                                v
                    +----------------------+
                    |      HolmesGPT       |
                    | namespace: holmesgpt |
                    | kb_tools.py          |
                    +----------------------+
```

## Namespace Layout

### Hub Cluster

- `sre-exporters`
  New exporters that write raw artifacts to cloud S3.

- `sre-system`
  New embedding service and normalizer.

- `holmesgpt`
  HolmesGPT deployment plus `kb_tools.py` config and S3/Qdrant access.

- `qdrant`
  Shared vector store.

- `kb-system`
  Legacy MinIO-based stack. This is no longer the active collection path and its CronJobs are expected to stay suspended.

### Spoke Cluster

- `sre-exporters`
  Exporters that write raw artifacts to cloud S3.

- `k8sgpt-operator-system`
  `k8sgpt` operator and scanner.

## Identity Model

Cluster identity is carried by `CLUSTER_ID`.

Examples:
- `hub`
- `spoke-a`

That value appears in:
- exporter environment
- S3 raw object keys
- normalized S3 object keys
- Qdrant collection names
- HolmesGPT search target selection

## Data Contracts

### Raw S3 Keys

```text
raw/<tool>/<cluster_id>/<timestamp>/<filename>
```

Examples:
- `raw/k8sgpt/spoke-a/20260323T185439Z/results.json`
- `raw/kubescape/hub/20260323T190259Z/findings.json`

### Normalized S3 Keys

```text
normalized/docs/<cluster_id>/<timestamp>/docs.jsonl
```

### Qdrant Collections

```text
kb_docs_<cluster_id>
```

Examples:
- `kb_docs_hub`
- `kb_docs_spoke-a`

## Operational Meaning

If a cluster is working in the new architecture, you should be able to trace one artifact through all stages:

1. exporter uploaded `raw/.../<cluster_id>/...`
2. normalizer wrote `normalized/docs/<cluster_id>/...`
3. Qdrant payload contains:
- `cluster_id=<cluster_id>`
- `source_key=raw/.../<cluster_id>/...`
4. HolmesGPT search returns the same `source_key`
