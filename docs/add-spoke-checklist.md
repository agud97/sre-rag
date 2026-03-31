# Add Spoke Checklist

Per-spoke ArgoCD model:

1. Create `cluster-identity` in namespace `sre-exporters` from `templates/cluster-identity.yaml`.
2. Set `CLUSTER_ID` in that ConfigMap to the stable cluster name.
3. In the spoke cluster, create `s3-credentials` in namespace `sre-exporters`.
4. In the spoke cluster ArgoCD, apply:
- `applications/spoke-common-k8sgpt.yaml`
- `applications/spoke-common-k8sgpt-scanner.yaml`
- `applications/spoke-common-sre-rag.yaml`
5. Trigger one exporter job manually and verify objects appear under `raw/`.
6. Trigger `normalizer` on Hub and verify a new Qdrant collection is created.
