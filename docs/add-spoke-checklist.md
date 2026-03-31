# Add Spoke Checklist

Per-spoke ArgoCD model:

1. Copy `applications/spoke-a-sre-rag.yaml` to `applications/<new-spoke>-sre-rag.yaml`.
2. Change the inline `source.kustomize.patches` value for `CLUSTER_ID`.
3. Create:
- `applications/<new-spoke>-k8sgpt.yaml`
- `applications/<new-spoke>-k8sgpt-scanner.yaml`
- `applications/<new-spoke>-sre-rag.yaml`
4. In the spoke cluster, create `s3-credentials` in namespace `sre-exporters`.
5. In the spoke cluster ArgoCD, apply the `k8sgpt` operator app, then the scanner app, then the SRE RAG app.
6. Trigger one exporter job manually and verify objects appear under `raw/`.
7. Trigger `normalizer` on Hub and verify a new Qdrant collection is created.
