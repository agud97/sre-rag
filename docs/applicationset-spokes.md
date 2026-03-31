# ApplicationSet Layout For Many Spokes

This repository now includes a draft `ApplicationSet` layout for scaling spoke rollouts.

Files:
- `apps/applicationsets/spokes-sre-rag.yaml`
- `apps/applicationsets/spokes-k8sgpt-scanner.yaml`
- `clusters/spokes/*.yaml`

## Intent

The goal is to stop creating one handwritten ArgoCD `Application` per spoke cluster.

Instead:
- one `ApplicationSet` generates the spoke exporters application for every spoke
- one `ApplicationSet` generates the `k8sgpt` scanner application for every spoke
- the source of truth for the spoke list becomes `clusters/spokes/*.yaml`

## Inventory Contract

Each spoke inventory file currently contains:
- `name`
- `cluster_id`
- `argo_cluster`
- `overlay`

Current examples:
- `clusters/spokes/spoke-a.yaml`

Only clusters with a real ArgoCD destination registration should exist in `clusters/spokes/`.

At the moment the live inventory keeps only `spoke-a` active so the generated `ApplicationSet` resources stay deployable on the current experimental stand.

`argo_cluster` is the ArgoCD destination cluster name as registered in the ArgoCD cluster secret.

`overlay` currently still points to a per-spoke Kustomize overlay.

## Current Scope

`spoke-a` is now cut over to the `ApplicationSet` model for:
- SRE exporters
- `k8sgpt` scanner custom resource

The `spoke-b` examples remain part of the legacy handwritten application model, but are not included in the new live `ApplicationSet` inventory until that cluster is actually registered in hub ArgoCD.

The repository still intentionally keeps the separate `k8sgpt` operator installation pattern.

## Next Migration Step

For a real `100+` spoke rollout, the next useful simplification would be:
- replace per-spoke overlays with a parameterized shared spoke template
- keep `clusters/spokes/*.yaml` as the inventory
- let `ApplicationSet` drive all generated spoke applications from that inventory
