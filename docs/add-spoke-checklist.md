# Add Spoke Checklist

Current live model:

1. Register the remote cluster in hub ArgoCD.
2. Ensure the `k8sgpt` operator exists in that spoke cluster.
3. Create `s3-credentials` in namespace `sre-exporters` in that spoke cluster.
4. Add `clusters/spokes/<new-spoke>.yaml`.
5. Push to `main` and let `ApplicationSet` generate:
- `<new-spoke>-sre-rag`
- `<new-spoke>-k8sgpt-scanner`
6. Trigger one exporter job manually and verify objects appear under `raw/`.
7. Trigger `normalizer` on Hub and verify a new Qdrant collection is created.

For the concrete `spoke-b` procedure, use:
- `docs/connect-spoke-b.md`
