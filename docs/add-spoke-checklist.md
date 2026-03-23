# Add Spoke Checklist

1. Copy `overlays/spoke-a` to `overlays/<new-spoke>`.
2. Change `CLUSTER_ID` in the new overlay config.
3. Create `applications/<new-spoke>-sre-rag.yaml`.
4. Create `applications/<new-spoke>-k8sgpt.yaml`.
5. Create `applications/<new-spoke>-k8sgpt-scanner.yaml`.
6. Create `s3-credentials` in namespace `sre-exporters`.
7. Apply the `k8sgpt` operator app, then the scanner app, then the SRE RAG app.
8. Trigger one exporter job manually and verify objects appear under `raw/`.
9. Trigger `normalizer` on Hub and verify a new Qdrant collection is created.
