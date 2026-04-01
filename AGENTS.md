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

### 3. Holmes Toolset Needed Multiple Fixes

The first visible bug was real but not the full root cause.

Initial symptom:
- Holmes `/api/chat` logged `Toolset 'kb/stack' is invalid`

First fix:
- `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml` needed a top-level `description`

But that alone was not enough.

Confirmed deeper root cause from live runtime:
- Holmes loaded `kb/stack` as `enabled`, but with `0 tools`
- direct `kb_tools.py search` still worked because `/kb-scripts/kb_tools.py` was mounted correctly
- Holmes chat still did not expose `kb_search` or `kb_fetch` to the LLM

Why:
- the separate mounted file ` /app/holmes/plugins/toolsets/kb-stack-toolset.yaml` was not the effective source of truth for Holmes chat tool-calling on this chart/runtime
- Holmes actually built the live custom toolset set from `/etc/holmes/config/custom_toolset.yaml`
- therefore `kb/stack` had to be defined inside `applications/hub-holmesgpt.yaml` under Helm `toolsets:`
- the mounted `kb-stack-toolset.yaml` remains only as the carrier for `kb_tools.py`, not the live Holmes chat tool definition

Second live bug inside that definition:
- Holmes YAML custom tools require `command` as a string or `script`, not a list of argv
- when `command` was rendered as a YAML list, Holmes marked `kb/stack` invalid at runtime and `kb_search`/`kb_fetch` again disappeared from `tools_by_name`

Final working fix:
- define `kb/stack` in `applications/hub-holmesgpt.yaml`
- keep `kb_tools.py` in `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml`
- use Holmes-valid `script` wrappers for `kb_search` and `kb_fetch` so multi-word queries survive shell quoting

Confirmed live behavior after the fix:
- `kb_search` and `kb_fetch` appear in Holmes `tools_by_name`
- direct Holmes `/api/chat` uses `kb_search`
- Open WebUI path also returns KB-backed artifact keys through Holmes

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

### 5. Open WebUI And Holmes KB Path Had Additional Runtime Traps

Confirmed live findings:
- the Open WebUI Pipe model id for HTTP use is `holmes_sre_agent.holmes_sre_agent`, not just `holmes_sre_agent`
- Open WebUI transport was healthy before Holmes KB tool selection was healthy
- once `kb/stack` was loaded correctly, Holmes `/api/chat` switched from `kubectl_*` investigation to real `kb_search` tool calls for KB lookup prompts

Known cosmetic issue:
- the Pipe can still render `Executed tools` as `unknown` because Holmes tool-call objects do not always match the Pipe's current formatting assumptions
- this does not block retrieval or chat correctness

### 6. Holmes S3 Secret Stub Caused Rollout Regressions

Important operational finding:
- `holmesgpt-configs` previously synced an empty `holmesgpt/s3-credentials-normalizer` Secret stub from git
- after a sync or restart, new Holmes pods could fail with `couldn't find key accessKeyId in Secret holmesgpt/s3-credentials-normalizer`

Fix:
- remove the empty `Secret` from `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml`
- keep the live `holmesgpt/s3-credentials-normalizer` Secret managed out of band
- never reintroduce an empty git stub for that Secret in this repo

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

Check that Holmes really exposes KB tools to the LLM:
```bash
KUBECONFIG=/root/proj/cross/kubeconfig_6005021 kubectl -n holmesgpt exec deploy/holmesgpt-holmes -- /venv/bin/python - <<'PY'
from holmes.config import Config
cfg = Config.load_from_env()
ai = cfg.create_toolcalling_llm(dal=None, model=None)
print("kb_search" in ai.tool_executor.tools_by_name)
print("kb_fetch" in ai.tool_executor.tools_by_name)
PY
```

Check Holmes chat direct over HTTP:
```bash
KUBECONFIG=/root/proj/cross/kubeconfig_6005021 kubectl -n holmesgpt port-forward svc/holmesgpt-holmes 15052:80
curl -sS -X POST http://127.0.0.1:15052/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"ask":"Return one recent kubescape artifact key for hub and one for spoke-a. Keep the answer to two lines and include only the keys."}' | jq
```

Check Open WebUI HTTP path with the Pipe model:
```bash
KUBECONFIG=/root/proj/cross/kubeconfig_6005021 kubectl -n open-webui port-forward svc/open-webui 18082:80
curl -sS -X POST http://127.0.0.1:18082/api/chat/completions \
  -H 'Authorization: Bearer <OPENWEBUI_JWT>' \
  -H 'Content-Type: application/json' \
  -d '{"model":"holmes_sre_agent.holmes_sre_agent","messages":[{"role":"user","content":"Return one recent kubescape artifact key for hub and one for spoke-a. Keep the answer to two lines and include only the keys."}],"stream":false}' | jq
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
- for Holmes custom tools, verify what the live runtime actually reads; a mounted helper file is not automatically the same thing as a loaded toolset
- if you need to validate Open WebUI, distinguish carefully between:
  - raw collection
  - normalization/Qdrant retrieval
  - Holmes `/api/chat`
  - Open WebUI Pipe execution
  - upstream LLM availability

## Current Known Cleanup Items

- `open-webui/functions/__pycache__/` is untracked local junk
- spoke legacy overlays can remain for reference, but should not be described as active rollout
- Holmes `prometheus/metrics` should stay disabled until the VictoriaMetrics backend is fixed; current `vmsingle` storage is pinned to NotReady node `k8s6005021-az1-md1-5rhzt-477v8`
- historical failed `normalizer` jobs may still need manual cleanup until the new `concurrencyPolicy: Forbid` cycle ages them out
