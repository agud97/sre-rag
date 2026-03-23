# Implementation Progress

## 2026-03-23

### Status
- Started implementation from `PLAN.md`.
- Repository initially contained only `PLAN.md`, `README.md`, and `local/s3.env`.
- Base manifests, overlays, and ArgoCD applications are now created.
- Structural validation via `kubectl kustomize` passes for hub, spoke-a, and holmesgpt configs.

### Decisions Applied
- One shared S3 credential set is used for exporters, normalizer, and HolmesGPT.
- `sre-rag-config` is created separately in each namespace that consumes it.
- `k8sgpt` is part of the spoke rollout.
- `kubevious` is excluded from the current implementation to remove scope ambiguity.

### Current Work
- Final repository cleanup and documentation alignment.

### Problems And Resolutions
- Problem: `PLAN.md` described cross-namespace reuse of `sre-rag-config`, which is not valid in Kubernetes.
- Resolution: create namespace-local `sre-rag-config` objects for `sre-exporters`, `sre-system`, and `holmesgpt`.

- Problem: repository does not contain source manifests from `idp-app-v1`.
- Resolution: build a clean standalone implementation directly from the target architecture and requirements.

- Problem: `local/s3.env` has an empty `S3_REGION`.
- Resolution: use explicit fallback `us-east-1` in ConfigMaps and keep application code tolerant to missing region values.

- Problem: spoke cluster does not have `k8sgpt` installed, and the initial exporter manifests used the wrong CRD group.
- Resolution: corrected `k8sgpt` CRD references to `core.k8sgpt.ai`, added ArgoCD applications for the `k8sgpt` operator and scanner resource.

- Problem: existing Hub `holmesgpt` deployment still mounts runbook ConfigMaps that were absent from the new app spec.
- Resolution: preserved those mounts in the new `hub-holmesgpt.yaml` while switching storage integration from MinIO to S3.

- Problem: `holmesgpt-configs` historically owned additional runbook resources not present in the new repo path.
- Resolution: disable pruning for `holmesgpt-configs` so ArgoCD does not delete legacy runbook ConfigMaps required by the live HolmesGPT deployment.

- Problem: `kubescape/kubescape:latest` on Docker Hub does not exist, causing `ErrImagePull` in the exporter validation job.
- Resolution: switch exporter image to pinned `quay.io/kubescape/kubescape:v3.0.31`, which resolves successfully.

### Next Steps
- Optional next execution step is cluster deployment and runtime verification.
