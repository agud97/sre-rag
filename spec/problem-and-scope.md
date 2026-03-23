# Problem And Scope

## Problem

The project builds a shared knowledge pipeline for Kubernetes cluster diagnostics.

The target outcome is:
- collect machine-readable cluster findings from multiple clusters
- store raw exporter outputs in a shared cloud S3 bucket
- normalize those raw artifacts into searchable documents
- index those documents in Qdrant per cluster
- make them available to HolmesGPT tools for retrieval during investigations

The system is intended to replace a legacy MinIO-based single-stack flow with a cleaner multi-cluster model.

## What The System Solves

The system gives operators and HolmesGPT a consistent way to answer questions such as:
- what security findings exist in cluster `spoke-a`
- what did `popeye` report for `hub`
- what `k8sgpt` findings are known for a given cluster
- where is the raw source artifact for a search result

It also provides a repeatable rollout model for adding more spoke clusters.

## In Scope

- exporters for `kubescape`, `popeye`, and `k8sgpt`
- shared cloud S3 bucket for raw and normalized artifacts
- hub-side embedding and normalization pipeline
- Qdrant collections per cluster
- HolmesGPT knowledge tools that search the indexed data
- ArgoCD-managed deployment model
- separate overlays for hub and spoke clusters

## Out Of Scope

- automatic cluster discovery
- automatic provisioning of S3 credentials
- storing real secrets in git
- preserving legacy MinIO compatibility
- `kubevious` in the new architecture
- a generic UI for browsing artifacts outside HolmesGPT and standard tools

## Current Naming Model

Cluster names are explicit configuration values, not auto-discovered identities.

Examples in the current implementation:
- `hub`
- `spoke-a`

Those names flow through:
- `CLUSTER_ID` in cluster config
- raw S3 keys like `raw/k8sgpt/spoke-a/...`
- normalized keys like `normalized/docs/spoke-a/...`
- Qdrant collections like `kb_docs_spoke-a`

## Success Criteria

The architecture is considered working when:
- exporters upload fresh raw artifacts to cloud S3
- the hub normalizer reads those artifacts and writes normalized docs
- Qdrant contains payloads with the expected `cluster_id`, `tool`, and `source_key`
- HolmesGPT can return search hits that point back to those raw artifacts
