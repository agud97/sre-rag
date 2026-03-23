# Change Guide

## Principles

- keep cluster identity explicit through `CLUSTER_ID`
- keep raw artifact key shapes stable
- keep Qdrant collection naming stable
- never store real credentials in git
- prefer additive migration over in-place destructive changes

## Safe Change Areas

Usually safe:
- adding a new spoke overlay
- adjusting schedules
- updating exporter images
- extending HolmesGPT tools
- adding new validation docs

Needs extra care:
- changing S3 key layout
- changing payload field names in the normalizer
- changing Qdrant collection naming
- changing `cluster_id` values for already indexed clusters
- changing secret names or key names

## How To Add A New Spoke

1. Copy `overlays/spoke-a` to `overlays/<new-name>`.
2. Set `CLUSTER_ID` to the desired stable identifier.
3. Create:
- `applications/<new-name>-k8sgpt.yaml`
- `applications/<new-name>-k8sgpt-scanner.yaml`
- `applications/<new-name>-sre-rag.yaml`
4. Create `s3-credentials` in `sre-exporters` in that cluster.
5. Sync `k8sgpt` operator, then scanner, then `sre-rag`.
6. Trigger at least one exporter job manually.
7. Run the hub normalizer.
8. Confirm a new Qdrant collection `kb_docs_<new-name>` appears.

## How To Change Cluster Identity

Do not rename a cluster casually.

Changing `CLUSTER_ID` changes:
- raw S3 prefixes
- normalized S3 prefixes
- Qdrant collection names
- HolmesGPT query target

If a rename is necessary:
- treat it as a data migration
- decide whether old data will be preserved, reindexed, or discarded

## How To Add A New Exporter

1. Add a new base manifest under `base/exporters/<tool>/`.
2. Keep the same raw key convention:
- `raw/<tool>/${CLUSTER_ID}/${timestamp}/...`
3. Ensure output is valid JSON or text that the normalizer can wrap safely.
4. Update docs in `spec/`.
5. Run a manual exporter job.
6. Run the normalizer and confirm Qdrant payloads for the new tool.

## How To Change The Normalizer

Be careful with:
- `parse_key`
- `docs_from_object`
- payload field names
- collection naming

Any change here affects:
- indexing
- HolmesGPT search behavior
- future compatibility of existing documents

When changing the normalizer:
- run it manually in hub
- inspect `normalized/docs/...`
- inspect Qdrant payloads directly
- validate HolmesGPT search results

## Legacy Cleanup Rules

The old `kb-system` stack should be removed only after:
- new exporters are confirmed for the hub cluster
- new normalizer is confirmed for hub and spokes
- Qdrant contains the expected new payloads
- HolmesGPT uses the new toolset successfully

Until then:
- prefer `suspend=true` for old CronJobs
- avoid destructive cleanup of shared components unless the migration is already validated
