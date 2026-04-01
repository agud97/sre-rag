# AGENTS.md

## Project Snapshot

This repository is `sre-rag`: a multi-cluster SRE knowledge base for Kubernetes.

Current active architecture:
- raw findings are collected by exporters in `sre-exporters`
- raw objects are uploaded to S3 under `raw/<tool>/<cluster_id>/<timestamp>/...`
- hub `normalizer` in `sre-system` writes normalized snapshots to `normalized/docs/<cluster_id>/<timestamp>/docs.jsonl`
- hub `normalizer` also upserts vectors into Qdrant collections `kb_docs_<cluster_id>`
- HolmesGPT in `holmesgpt` uses `kb_tools.py` to search Qdrant and fetch S3 artifacts
- Open WebUI can expose Holmes through the `Holmes SRE Agent` Pipe function

## Rollout Model

Active rollout model is `Per-spoke ArgoCD`.

Hub ArgoCD bootstrap:
- root app `apps` now points to `https://github.com/agud97/sre-rag.git` path `applications`
- `applications/apps.yaml` is the bootstrap manifest for that root app
- automated prune is intentionally disabled there to avoid deleting legacy non-`sre-rag` `Application` resources during cutover
- on hub, root app must exclude `applications/spoke-common-sre-rag.yaml`, otherwise it creates a duplicate child app `sre-rag` that conflicts with `hub-sre-rag` over exporter resources

Hub:
- `applications/hub-sre-rag.yaml`
- `applications/hub-qdrant.yaml`
- `applications/hub-holmesgpt.yaml`
- `applications/hub-holmesgpt-configs.yaml`

Spokes:
- every spoke runs its own ArgoCD
- every spoke applies the same shared apps:
  - `applications/spoke-common-k8sgpt.yaml`
  - `applications/spoke-common-k8sgpt-scanner.yaml`
  - `applications/spoke-common-sre-rag.yaml`
- every spoke also creates `sre-exporters/cluster-identity`

Important:
- `overlays/spoke-a` and `overlays/spoke-b` still exist in git, but they are legacy reference only
- active spoke rollout path is `templates/spoke-exporters` + `templates/cluster-identity.yaml` + shared `applications/spoke-common-*.yaml`

## Live Cluster Context

Known kubeconfigs:
- hub: `/root/proj/cross/kubeconfig_6005021`
- spoke-a: `/root/codex/kubeconfig_6144665`

Confirmed live state as of 2026-04-01:
- `hub` is both hub and spoke
- `spoke-a` is connected and active
- raw data collection is healthy for both `hub` and `spoke-a`
- targeted normalized snapshots were written for both `hub` and `spoke-a`
- Qdrant collections exist for:
  - `kb_docs_hub`
  - `kb_docs_spoke-a`

There is no confirmed live `spoke-b` yet.

## Important File Paths

Shared spoke runtime:
- `templates/spoke-exporters/kustomization.yaml`
- `templates/spoke-exporters/cluster-config.yaml`
- `templates/cluster-identity.yaml`

Hub runtime:
- `overlays/hub/kustomization.yaml`
- `overlays/hub/cluster-config-exporters.yaml`
- `overlays/hub/cluster-identity-exporters.yaml`
- `overlays/hub/cluster-config-system.yaml`

Normalizer:
- `base/hub/normalizer/cronjob.yaml`
- `base/hub/normalizer/script-configmap.yaml`

Holmes toolset:
- `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml`
- `open-webui/functions/holmes_sre_agent.py`

## Operational Findings From The Last Session

### 1. Embedding Service Is Slow

`embedding-svc` is working, but very slow on the current CPU setup.

Observed behavior:
- embedding 2 tiny texts took about 48 seconds
- full hourly `normalizer` can lag or appear stuck because it tries to process the whole backlog

This is why a targeted manual reindex was used on the stand.

### 2. Targeted Manual Reindex Was Needed

Full backlog ingest was not reliable enough for fresh validation.

What was done:
- a temporary pod `normalizer-targeted` was created in `sre-system`
- it was pinned to healthy node `k8s6005021-az1-md1-5rhzt-jlllw`
- the script ingested only the latest `kubescape`, `k8sgpt`, and `popeye` raw objects for `hub` and `spoke-a`

Result:
- new normalized snapshots were written for both clusters
- Qdrant point counts increased
- Holmes `kb_tools.py search` started returning fresh `20260331...` keys

### 3. Holmes Toolset Needed A Fix

`kb-stack-toolset.yaml` must include a top-level `description`.

Without it:
- Holmes `/api/chat` logs `Toolset 'kb/stack' is invalid`
- direct `kb_tools.py search` may still work
- Open WebUI Pipe can still fail because Holmes chat does not load the toolset correctly

This was fixed in:
- `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml`

### 4. Holmes Chat Was Fixed To Use External LiteLLM

Current Holmes model config:
- `MODEL=openai/minimax-m25`
- `OPENAI_API_BASE=http://89.111.168.161:32080/v1`

Confirmed live behavior:
- direct `POST /api/chat` on Holmes returns `200`
- Holmes startup no longer logs `Toolset 'kb/stack' is invalid`
- Holmes logs show `Loaded models: ['openai/minimax-m25']`
- Holmes can call LiteLLM successfully when the endpoint is reachable

Meaning:
- retrieval and chat are now independently confirmed healthy
- if Open WebUI still fails, debug the Pipe layer separately from Holmes

## Useful Verification Commands

Hub apps:
```bash
KUBECONFIG=/root/proj/cross/kubeconfig_6005021 kubectl -n argocd get applications
```

Spoke-a apps:
```bash
KUBECONFIG=/root/codex/kubeconfig_6144665 kubectl -n argocd get applications
```

Check fresh raw objects via exporters:
```bash
KUBECONFIG=/root/proj/cross/kubeconfig_6005021 kubectl -n sre-exporters get cronjobs
KUBECONFIG=/root/codex/kubeconfig_6144665 kubectl -n sre-exporters get cronjobs
```

Check Holmes retrieval directly:
```bash
KUBECONFIG=/root/proj/cross/kubeconfig_6005021 kubectl -n holmesgpt exec deploy/holmesgpt-holmes -- python3 /kb-scripts/kb_tools.py search kubescape 5 hub
KUBECONFIG=/root/proj/cross/kubeconfig_6005021 kubectl -n holmesgpt exec deploy/holmesgpt-holmes -- python3 /kb-scripts/kb_tools.py search kubescape 5 spoke-a
```

Check external LiteLLM directly:
```bash
curl -sS http://89.111.168.161:32080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer 6eedf0a5927e06569b11d6c51c29d950da4a69d0f7061ac8' \
  -d '{"model":"minimax-m25","messages":[{"role":"user","content":"ping"}]}' | jq
```

## Git And Credentials

GitHub token path:
- `/root/codex/token-gh`

Example push pattern that worked:
```bash
TOKEN=$(cat /root/codex/token-gh)
git remote set-url origin https://oauth2:${TOKEN}@github.com/agud97/sre-rag.git
git push origin main
```

## Editing Rules For Future Sessions

- do not revert user changes unless explicitly asked
- use `apply_patch` for repo file edits
- keep docs aligned with the real live model, not with older `ApplicationSet` experiments
- if you need to validate Open WebUI, distinguish carefully between:
  - raw collection
  - normalization/Qdrant retrieval
  - Holmes `/api/chat`
  - Open WebUI Pipe execution
  - upstream LLM availability

## Current Known Cleanup Items

- `open-webui/functions/__pycache__/` is untracked local junk
- spoke legacy overlays can remain for reference, but should not be described as active rollout
- Holmes `prometheus/metrics` toolset still fails to initialize against VictoriaMetrics
- historical failed `normalizer` jobs may still need manual cleanup until the new `concurrencyPolicy: Forbid` cycle ages them out
