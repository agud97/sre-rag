# sre-rag

Multi-cluster SRE knowledge base for Kubernetes clusters.

Components:
- Exporters for `kubescape`, `popeye`, and `k8sgpt`
- Hub services for embeddings and normalization
- Qdrant and HolmesGPT ArgoCD applications
- Open WebUI Pipe Function for `Holmes SRE Agent`
- Per-spoke ArgoCD rollout using shared spoke `Application` manifests

Repository layout:
- `base/` shared manifests
- `overlays/` hub overlay plus legacy spoke overlays kept only as reference
- `applications/` ArgoCD Application resources
- `templates/` shared spoke exporter template and `cluster-identity` template
- `docs/` operational notes
- `spec/` task description, technical spec, runbooks, and user documentation
- `IMPLEMENTATION_PROGRESS.md` execution log for this rollout

Secrets are created manually in-cluster. Real credentials are not stored in git.

Current rollout model:
- hub runs `hub-sre-rag`, `qdrant`, `holmesgpt`, and `holmesgpt-configs`
- each spoke runs its own ArgoCD
- each spoke applies the same shared apps:
  - `applications/spoke-common-k8sgpt.yaml`
  - `applications/spoke-common-k8sgpt-scanner.yaml`
  - `applications/spoke-common-sre-rag.yaml`
- each spoke provides its own `sre-exporters/cluster-identity` `ConfigMap`

Current operational caveats:
- raw data collection from `hub` and `spoke-a` is healthy
- Qdrant retrieval works for `hub` and `spoke-a`
- full hourly `normalizer` can lag because `embedding-svc` is slow on CPU; targeted manual reindex may be needed during incidents
- Open WebUI depends on HolmesGPT, and HolmesGPT currently depends on an external LiteLLM endpoint at `http://89.111.168.161:32080/v1`; if that upstream LLM path is timing out, the Pipe model will fail even when S3, normalizer, and Qdrant are healthy

Start with:
- `spec/README.md`
- `spec/technical-implementation.md`
- `spec/user-guide-holmesgpt.md`
- `docs/open-webui-holmes-sre-agent.md`
