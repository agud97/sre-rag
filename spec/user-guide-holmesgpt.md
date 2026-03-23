# User Guide: Validate The System And Use HolmesGPT

## What This System Gives You

HolmesGPT can search findings collected from Kubernetes clusters.

Today the supported data sources are:
- `kubescape`
- `popeye`
- `k8sgpt`

Search results point back to the raw artifact in S3 through `source_key`.

## Before You Start

The system is working only if all stages are healthy:
- exporters upload raw data to cloud S3
- the hub normalizer indexes that data
- Qdrant stores the normalized documents
- HolmesGPT uses the new knowledge toolset

## How To Check That Everything Works

### Check 1: Raw Data Exists In S3

For each cluster you expect to use, there should be raw objects like:
- `raw/kubescape/<cluster>/...`
- `raw/popeye/<cluster>/...`
- `raw/k8sgpt/<cluster>/...`

Examples:
- `raw/k8sgpt/spoke-a/...`
- `raw/kubescape/hub/...`

### Check 2: Normalized Data Exists

There should also be normalized snapshots:
- `normalized/docs/<cluster>/.../docs.jsonl`

This means the hub normalizer processed the raw artifacts.

### Check 3: Qdrant Contains Cluster Data

For every active cluster, there should be a Qdrant collection:
- `kb_docs_hub`
- `kb_docs_spoke-a`

If a collection is missing, HolmesGPT will not be able to search that cluster.

### Check 4: HolmesGPT Search Returns S3-Backed Results

A healthy result looks like:

```text
[score=...] tool=k8sgpt ts=20260323T185439Z key=raw/k8sgpt/spoke-a/20260323T185439Z/results.json
```

The important part is the `key=raw/...` value. It proves the answer is backed by the indexed artifact pipeline.

## How To Use HolmesGPT

### Search A Specific Cluster

Use the knowledge tool with an explicit cluster name.

Examples:
- search for security findings in `spoke-a`
- search for `k8sgpt` findings in `hub`
- search for `popeye` warnings in `spoke-a`

Operationally, the underlying command is:

```bash
python3 /kb-scripts/kb_tools.py search "<query>" <limit> <cluster_id>
```

Example:

```bash
python3 /kb-scripts/kb_tools.py search "k8sgpt" 10 spoke-a
```

## Important Behavior

If `cluster_id` is omitted, the current implementation defaults to:
- `hub`

That means a user asking a vague question without specifying a cluster may only search the hub collection.

## Recommended User Query Style

Be explicit:
- mention the cluster name
- mention the tool if you know it
- ask for the raw source if you want to inspect the original finding

Good examples:
- `Show kubescape findings for spoke-a`
- `Search k8sgpt problems in hub`
- `Find popeye issues for spoke-a and give me the artifact key`

Weak examples:
- `What clusters are bad right now`
- `Search everything`

Those can work poorly because the current toolset does not yet have a dedicated cluster discovery command.

## How To Interpret Results

A result includes:
- `tool`
- `ts`
- `key`

Meaning:
- `tool` — which exporter produced the document
- `ts` — artifact timestamp
- `key` — exact S3 object path for the raw artifact

If you need the original machine-readable artifact, use `key`.

## Known Limitations

- cluster names are configured manually through `CLUSTER_ID`
- there is no first-class `list_clusters` command yet
- default search without `cluster_id` uses the hub collection
- repeated results can appear because one artifact can produce multiple indexed points

## What To Report If Something Looks Wrong

When opening an issue, include:
- cluster name
- tool name
- expected raw S3 prefix
- actual HolmesGPT query
- one example result or absence of results
- whether `normalized/docs/<cluster>/...` exists

This is usually enough to localize the fault to exporters, normalizer, Qdrant, or HolmesGPT config.
