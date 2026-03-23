# sre-rag

Multi-cluster SRE knowledge base for Kubernetes clusters.

Components:
- Exporters for `kubescape`, `popeye`, and `k8sgpt`
- Hub services for embeddings and normalization
- Qdrant and HolmesGPT ArgoCD applications

Repository layout:
- `base/` shared manifests
- `overlays/` per-cluster configuration
- `applications/` ArgoCD Application resources
- `docs/` operational notes
- `IMPLEMENTATION_PROGRESS.md` execution log for this rollout

Secrets are created manually in-cluster. Real credentials are not stored in git.
