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
- `clusters/spokes/spoke-b.yaml`

`argo_cluster` is the ArgoCD destination cluster name as registered in the ArgoCD cluster secret.

`overlay` currently still points to a per-spoke Kustomize overlay.

## Current Scope

This is a draft migration scaffold, not a full cutover yet.

It intentionally does not remove:
- `applications/spoke-a-sre-rag.yaml`
- `applications/spoke-b-sre-rag.yaml`
- `applications/spoke-a-k8sgpt-scanner.yaml`
- `applications/spoke-b-k8sgpt-scanner.yaml`

It also intentionally does not replace the separate `k8sgpt` operator installation pattern yet.

## Next Migration Step

For a real `100+` spoke rollout, the next useful simplification would be:
- replace per-spoke overlays with a parameterized shared spoke template
- keep `clusters/spokes/*.yaml` as the inventory
- let `ApplicationSet` drive all generated spoke applications from that inventory
