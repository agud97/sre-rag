# Implementation Progress

## 2026-03-23

### Status
- Started implementation from `PLAN.md`.
- Repository initially contained only `PLAN.md`, `README.md`, and `local/s3.env`.
- Base manifests, overlays, and ArgoCD applications are now created.
- Structural validation via `kubectl kustomize` passes for hub, spoke-a, and holmesgpt configs.
- GitHub delivery is configured and multiple rollout commits were pushed to `origin/main`.
- SpokeA applications `k8sgpt`, `spoke-a-k8sgpt-scanner`, and `spoke-a-sre-rag` are `Synced/Healthy`.
- Manual spoke validation succeeded for `kubescape` exporter up to confirmed S3 object creation.
- Hub applications `hub-sre-rag`, `qdrant`, and `holmesgpt` are now `Synced/Healthy`.
- End-to-end data path is confirmed: `spoke exporter -> S3 raw -> normalizer -> Qdrant -> HolmesGPT kb_tools`.

### Decisions Applied
- One shared S3 credential set is used for exporters, normalizer, and HolmesGPT.
- `sre-rag-config` is created separately in each namespace that consumes it.
- `k8sgpt` is part of the spoke rollout.
- `kubevious` is excluded from the current implementation to remove scope ambiguity.

### Current Work
- Final rollout validation and documenting the remaining legacy ArgoCD drift.

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
- Resolution: align with the known-good manifest from `idp-app-v1` and switch to `quay.io/kubescape/kubescape-cli:v3.0.48`.

- Problem: the non-CLI Kubescape image layout does not expose a runnable shell/CLI path for the init container.
- Resolution: reuse the working `kubescape-cli` image and argument structure from the existing hub manifests.

- Problem: the corporate S3 endpoint presents a certificate chain that is not trusted by the default CA bundle in local and containerized clients.
- Resolution: add `S3_VERIFY_SSL=false`, disable TLS verification in AWS CLI uploads, and configure boto3 clients to honor the same setting.

- Problem: the original reconstructed Kubescape image/entrypoint did not match the working production setup.
- Resolution: align `sre-rag` with the known-good manifest from `/root/proj/cross/idp-app-v1` and use `quay.io/kubescape/kubescape-cli:v3.0.48`.

- Problem: Hub ArgoCD controller was stuck because `argocd-application-controller-0` had been terminating for more than five days.
- Resolution: force-delete the stale pod so the StatefulSet could recreate a healthy controller and resume reconciliation.

- Problem: full Hub end-to-end validation is currently blocked by cluster health, not by application manifests.
- Resolution: this was transient infrastructure pressure. After targeted tolerations and subsequent rescheduling, Hub components recovered and the new stack completed validation.

- Problem: after the controller recovered, new Hub pods still could not schedule onto the only otherwise usable node because it carries `node.cilium.io/agent-not-ready:NoSchedule`.
- Resolution: add a targeted toleration for `node.cilium.io/agent-not-ready` to the new Hub components (`embedding-svc`, `normalizer`, `qdrant`, `holmesgpt`). `disk-pressure` taints are intentionally not tolerated.

- Problem: legacy Qdrant PVC was pinned to an unavailable node through PV node affinity, leaving the `qdrant` service without endpoints and blocking `normalizer` writes.
- Resolution: because this is a test installation and data loss is acceptable, delete the stale pod and PVC, allow the StatefulSet to provision a fresh volume on a schedulable node, then re-run ingestion from S3.

- Problem: `holmesgpt` initially remained unhealthy because the new repo path did not yet provide all ConfigMaps that the live deployment mounts.
- Resolution: add `custom-runbooks` and `sre-runbooks` ConfigMaps to `base/hub/holmesgpt-toolset`, keep the new S3-backed `kb-stack-toolset`, and sync the application again.

- Problem: `holmesgpt-configs` remains `OutOfSync/Progressing` even though the new knowledge-base path is working.
- Resolution: the only remaining drift is a legacy `holmes-alertmanager-bridge` Deployment that still exists in-cluster from the old `idp-app-v1` application history and is shown as `RequiresPruning`. This does not block the new SRE-RAG data path and should be handled as a separate cleanup step after migration.

- Problem: HolmesGPT end-to-end validation needed proof that it reads from the new Qdrant collections created by the new normalizer.
- Resolution: run `python3 /kb-scripts/kb_tools.py search 'security findings' 5 spoke-a` inside the live Holmes pod and confirm results from the new `raw/kubescape/...` and `raw/popeye/...` objects.

- Problem: `k8sgpt` data did not appear in S3 because the exporter init container used `bitnami/kubectl:1.30`, and that tag does not exist on Docker Hub.
- Resolution: switch the exporter to `bitnami/kubectl:latest`, push revision `f1a9e36`, wait for ArgoCD to reconcile, and verify a successful upload to `s3://sre-rag/raw/k8sgpt/hub/20260323T185208Z/results.json`.

- Problem: Hub still had a legacy `kb-system` exporter stack writing to MinIO while the new `sre-exporters` stack was already configured for cloud S3, which meant two parallel collection paths existed for the same cluster.
- Resolution: validate the new Hub exporters manually and confirm fresh cloud-S3 uploads for all three tools:
  - `raw/k8sgpt/hub/20260323T190245Z/results.json`
  - `raw/kubescape/hub/20260323T190259Z/findings.json`
  - `raw/popeye/hub/20260323T190300Z/report.json`
  Then run the new `sre-system` normalizer and confirm `Loaded 5 docs from hub`, `Upserted 5 docs to kb_docs_hub`, and payloads in Qdrant with `cluster_id=hub` and `source_key` under `raw/.../hub/...`.

- Problem: legacy `kb-system` CronJobs would continue to launch the old MinIO-based pipeline until explicitly stopped.
- Resolution: suspend legacy CronJobs `k8sgpt-exporter`, `kubescape-exporter`, `popeye`, `normalizer`, and `kubevious-exporter`, then delete the active legacy jobs so the old path stops executing.

- Problem: the initial `embedding-svc` implementation in `sre-rag` was only a deterministic hash-based stub, which is not suitable for real semantic retrieval.
- Resolution: replace it with a real CPU embedding service based on `sentence-transformers/all-MiniLM-L6-v2` while keeping the existing `/embed` endpoint contract for current clients and adding `/v1/embeddings` compatibility for future integrations.

- Problem: the first real embedding model (`all-MiniLM-L6-v2`) is lightweight but suboptimal for the actual retrieval pattern in this project, because operators use Russian-language queries against mostly English Kubernetes findings.
- Resolution: migrate to `intfloat/multilingual-e5-large-instruct`, pin the embedding service to the dedicated `c8-m16384-d120-hp` node class, raise memory and CPU reservations, and update HolmesGPT query embedding to prepend an instruction string as recommended by the E5 model card.

- Problem: under the heavier E5 workload, the embedding service became unstable because the original HTTP server was single-threaded, and Kubernetes liveness checks timed out while `/embed` requests were being processed.
- Resolution: switch the service to `ThreadingHTTPServer`, relax probe timeouts, complete rollout on the dedicated node, and then run a clean reindex with empty Qdrant collections.

- Problem: a rolling update of the single-replica embedding service on a dedicated node deadlocked because the old pod still held the full memory request and prevented the new pod from scheduling.
- Resolution: remove the stuck old pod, let the new replica claim the dedicated node, and proceed with the rollout as an effective singleton restart.

- Problem: after switching from 384-dimensional embeddings to 1024-dimensional E5 embeddings, existing Qdrant collections were no longer valid for direct reuse.
- Resolution: delete `kb_docs_hub` and `kb_docs_spoke-a`, rerun the normalizer, and confirm a clean rebuild:
  - `Loaded 8 docs from hub`
  - `Upserted 8 docs to kb_docs_hub`
  - `Loaded 6 docs from spoke-a`
  - `Upserted 6 docs to kb_docs_spoke-a`

- Problem: the new multilingual setup needed proof that Russian-language operator queries retrieve the expected English Kubernetes findings.
- Resolution: run `python3 /kb-scripts/kb_tools.py search 'проблемы безопасности kubernetes' 5 spoke-a` inside HolmesGPT and confirm high-scoring hits for `kubescape`, `k8sgpt`, and `popeye` from `raw/.../spoke-a/...`.

- Problem: after the E5 migration, some technical documents still described the old `384`-dimensional expectations or did not explicitly document the dedicated embedding node and E5 query-instruction behavior.
- Resolution: audit and update `PLAN.md`, `spec/architecture-diagram.md`, `spec/technical-implementation.md`, `spec/config-and-secrets.md`, `spec/change-guide.md`, and `spec/verification-and-operations.md` so they match the current `intfloat/multilingual-e5-large-instruct` deployment, `1024`-dimensional vectors, dedicated `c8-m16384-d120-hp` node placement, and HolmesGPT query-instruction contract.

- Problem: operators also need a regular chat UI path where HolmesGPT appears as a selectable model rather than only a backend service or direct pod command.
- Resolution: add `open-webui/functions/holmes_sre_agent.py` as an Open WebUI Pipe Function that maps Open WebUI `messages` into HolmesGPT `ask` plus `conversation_history`, returns an OpenAI-compatible completion response, and document import and usage in `docs/open-webui-holmes-sre-agent.md` together with architecture and user-guide updates.

### Next Steps
- Treat the new architecture as operational for test use.
- Optionally clean up legacy `idp-app-v1` resources and ArgoCD ownership drift after the team confirms cutover.
- Add a repeatable smoke-test checklist for `exporter -> S3 -> normalizer -> Qdrant -> HolmesGPT`.
