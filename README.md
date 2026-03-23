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
- `spec/` task description, technical spec, runbooks, and user documentation
- `IMPLEMENTATION_PROGRESS.md` execution log for this rollout

Secrets are created manually in-cluster. Real credentials are not stored in git.

Start with:
- `spec/README.md`
- `spec/technical-implementation.md`
- `spec/user-guide-holmesgpt.md`
