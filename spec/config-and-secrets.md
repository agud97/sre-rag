# Config And Secrets

## Configuration Model

Each consumer namespace gets its own `sre-rag-config` `ConfigMap`.

This is intentional because Kubernetes does not allow direct cross-namespace `ConfigMap` consumption.

Namespaces:
- `sre-exporters`
- `sre-system`
- `holmesgpt`

## Required Config Keys

### Exporters

Required in `sre-exporters/sre-rag-config`:
- `S3_ENDPOINT`
- `S3_BUCKET`
- `S3_REGION`
- `S3_VERIFY_SSL`

Examples:
- hub overlay keeps `CLUSTER_ID=hub`
- spoke exporters read `CLUSTER_ID` from `sre-exporters/cluster-identity`

Required in `sre-exporters/cluster-identity`:
- `CLUSTER_ID`

### Normalizer

Required in `sre-system/sre-rag-config`:
- `CLUSTER_ID`
- `S3_ENDPOINT`
- `S3_BUCKET`
- `S3_REGION`
- `S3_VERIFY_SSL`
- `QDRANT_ENDPOINT`
- `EMBEDDING_ENDPOINT`

Note:
- `CLUSTER_ID` is present for config consistency, but the normalizer groups documents by the `cluster_id` parsed from each S3 key.

### HolmesGPT

Required in `holmesgpt/sre-rag-config`:
- `S3_ENDPOINT`
- `S3_BUCKET`
- `S3_REGION`
- `S3_VERIFY_SSL`
- `QDRANT_ENDPOINT`
- `EMBEDDING_ENDPOINT`
- `EMBEDDING_QUERY_INSTRUCTION`

## Secret Model

Real credentials are not stored in git.

The repo contains only secret stubs:
- `s3-credentials` in `sre-exporters`
- `s3-credentials-normalizer` in `sre-system`
- `s3-credentials-normalizer` in `holmesgpt`

The current operating model uses the same S3 credential pair in all three places.

## Secret Keys

Expected keys:
- `accessKeyId`
- `secretAccessKey`

## S3 Key Layout

Raw artifacts:
- `raw/kubescape/<cluster_id>/<timestamp>/findings.json`
- `raw/popeye/<cluster_id>/<timestamp>/report.json`
- `raw/k8sgpt/<cluster_id>/<timestamp>/results.json`

Normalized docs:
- `normalized/docs/<cluster_id>/<timestamp>/docs.jsonl`

## Qdrant Naming

One collection per cluster:
- `kb_docs_hub`
- `kb_docs_spoke-a`

Payload fields written by the normalizer:
- `id`
- `cluster_id`
- `tool`
- `timestamp`
- `source_key`
- `text`

Embedding contract:
- current vector size is `1024`
- current production model is `intfloat/multilingual-e5-large-instruct`
- any future vector-size change requires new Qdrant collections or a full collection reset before reindex

## TLS Verification

The current S3 endpoint uses a certificate chain that is not trusted by the default container CA bundle.

Because of that, the current configuration uses:
- `S3_VERIFY_SSL=false`

This affects:
- AWS CLI uploads
- boto3 clients in the normalizer
- boto3 clients in HolmesGPT knowledge tools

If the endpoint certificate becomes trusted later, set:
- `S3_VERIFY_SSL=true`
and remove the `--no-verify-ssl` dependency from the runtime path.
