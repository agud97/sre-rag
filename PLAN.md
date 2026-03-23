# SRE-RAG: Мульти-кластерная Knowledge Base для SRE

## 0. Актуальные решения для реализации в этом репозитории

- Используется один и тот же набор S3 credentials для exporters, normalizer и HolmesGPT.
- `sre-rag-config` создаётся отдельно в каждом namespace-потребителе: `sre-exporters`, `sre-system`, `holmesgpt`.
- `k8sgpt` входит в состав spoke rollout.
- `kubevious` исключён из текущего implementation scope, даже если ниже в документе остались исторические упоминания.
- Фактический rollout в репозитории реализуется для трёх exporters: `kubescape`, `popeye`, `k8sgpt`.

## 1. Архитектура

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          Corporate S3 (bucket: sre-rag)                    │
│                                                                              │
│  raw/kubescape/{CLUSTER_ID}/{ts}/findings.json                              │
│  raw/popeye/{CLUSTER_ID}/{ts}/report.json                                   │
│  raw/k8sgpt/{CLUSTER_ID}/{ts}/results.json                                  │
│  raw/kubevious/{CLUSTER_ID}/{ts}/topology.json                              │
│  normalized/docs/{CLUSTER_ID}/{ts}/docs.jsonl                               │
└──────────────────┬──────────────────────────┬───────────────────────────────┘
                   │                          │
          S3 PUT (raw/)               S3 GET (raw/) + S3 PUT (normalized/)
                   │                          │
    ┌──────────────┴──────┐     ┌─────────────┴────────────────────────────┐
    │   SpokeA (spoke-a)  │     │           Hub (hub)                      │
    │   ns: sre-exporters │     │   ns: sre-system                         │
    │                     │     │                                           │
    │  kubescape-exporter │     │  ┌──────────────┐  ┌──────────────────┐  │
    │  (CronJob)          │     │  │ embedding-svc│  │   normalizer     │  │
    │                     │     │  │ Deployment   │  │   CronJob        │  │
    │  popeye-exporter    │     │  │ :7997        │  │   boto3→S3       │  │
    │  (CronJob)          │     │  └──────┬───────┘  │   →embed→Qdrant  │  │
    │                     │     │         │          └──────────────────┘  │
    │  k8sgpt-exporter    │     │         ▼                                │
    │  (CronJob)          │     │  ┌──────────────┐ ns: qdrant             │
    │                     │     │  │   Qdrant     │                        │
    │  ConfigMap:         │     │  │   :6333      │                        │
    │   sre-rag-config    │     │  └──────────────┘                        │
    │  Secret:            │     │                                           │
    │   s3-credentials    │     │  ┌──────────────┐ ns: holmesgpt           │
    │                     │     │  │  HolmesGPT   │                        │
    │  uploader:          │     │  │  + kb/stack  │                        │
    │  amazon/aws-cli     │     │  │    toolset   │                        │
    └─────────────────────┘     │  └──────────────┘                        │
                                │                                           │
                                │  ConfigMap: sre-rag-config               │
                                │  Secret: s3-credentials-normalizer       │
                                └──────────────────────────────────────────┘
                   │                          │
                   └──────── ArgoCD ──────────┘
                             │
              github.com/agud97/sre-rag.git
```

**Кластеры:**
- **Hub**: `KUBECONFIG=/root/proj/cross/kubeconfig_6005021` — Qdrant, embedding-svc, normalizer, HolmesGPT + exporters для самого hub
- **SpokeA**: `KUBECONFIG=/root/codex/kubeconfig_6144665` — только exporters

**Ключевые принципы:**
- MinIO удалён полностью, заменён на Corporate S3
- Uploader `minio/mc` заменён на `amazon/aws-cli`
- NetworkPolicy не используются
- Новый namespace: `sre-exporters` (exporters) и `sre-system` (hub services)
- Весь код в отдельном репозитории sre-rag (idp-app-v1 не модифицируется)

---

## 2. Структура репозитория sre-rag

```
sre-rag/
├── README.md
├── PLAN.md
│
├── base/
│   ├── exporters/                         # Общие манифесты exporters (hub + spoke)
│   │   ├── kustomization.yaml             # resources: namespace, kubescape, popeye, k8sgpt, rbac
│   │   ├── namespace.yaml                 # Namespace sre-exporters
│   │   ├── kubescape/
│   │   │   ├── kustomization.yaml
│   │   │   └── cronjob.yaml              # kubescape-exporter CronJob (aws-cli uploader)
│   │   ├── popeye/
│   │   │   ├── kustomization.yaml
│   │   │   └── cronjob.yaml              # popeye CronJob (aws-cli uploader)
│   │   ├── k8sgpt/
│   │   │   ├── kustomization.yaml
│   │   │   ├── cronjob.yaml              # k8sgpt-exporter CronJob (aws-cli uploader)
│   │   │   └── rbac.yaml                 # SA + ClusterRole + CRB для k8sgpt results
│   │   └── rbac/
│   │       ├── kustomization.yaml
│   │       ├── serviceaccounts.yaml      # SA: kubescape-exporter, popeye, k8sgpt-exporter
│   │       └── roles.yaml                # ClusterRole kb-readonly + bindings
│   │
│   └── hub/                              # Компоненты только для Hub
│       ├── kustomization.yaml            # resources: namespace, embedding-svc, normalizer, holmesgpt-toolset
│       ├── namespace.yaml                # Namespace sre-system
│       ├── embedding-svc/
│       │   ├── kustomization.yaml
│       │   └── embedding-svc.yaml        # ConfigMap (скрипт) + Deployment + Service
│       ├── normalizer/
│       │   ├── kustomization.yaml
│       │   ├── cronjob.yaml              # normalizer CronJob (boto3, AWS env vars)
│       │   └── script-configmap.yaml     # ConfigMap normalizer-script (normalize.py)
│       └── holmesgpt-toolset/
│           ├── kustomization.yaml
│           └── kb-stack-toolset.yaml     # ConfigMap kb-stack-toolset (toolset YAML + kb_tools.py)
│
├── overlays/
│   ├── hub/                              # Hub кластер overlay
│   │   ├── kustomization.yaml            # bases: ../../base/exporters + ../../base/hub + patches
│   │   └── cluster-config.yaml           # ConfigMap sre-rag-config (CLUSTER_ID=hub, S3 endpoint, etc.)
│   │
│   ├── spoke-a/                          # SpokeA overlay (только exporters)
│   │   ├── kustomization.yaml            # base: ../../base/exporters + patches
│   │   └── cluster-config.yaml           # ConfigMap sre-rag-config (CLUSTER_ID=spoke-a)
│   │
│   └── spoke-b/                          # Шаблон для нового spoke (скопировать, поменять CLUSTER_ID)
│       ├── kustomization.yaml
│       └── cluster-config.yaml
│
├── applications/                         # ArgoCD Application манифесты
│   ├── hub-sre-rag.yaml                  # ArgoCD App: Hub (path: overlays/hub)
│   ├── hub-qdrant.yaml                   # ArgoCD App: Qdrant Helm chart (Hub)
│   ├── hub-holmesgpt.yaml                # ArgoCD App: HolmesGPT Helm chart (Hub)
│   ├── hub-holmesgpt-configs.yaml        # ArgoCD App: HolmesGPT ConfigMaps (Hub)
│   └── spoke-a-sre-rag.yaml             # ArgoCD App: SpokeA exporters
│
└── docs/
    └── add-spoke-checklist.md            # Чеклист добавления нового spoke
```

**Описание ключевых файлов:**

| Файл | Назначение |
|------|-----------|
| `base/exporters/kubescape/cronjob.yaml` | CronJob: initContainer kubescape-cli scan, main container aws-cli s3 cp |
| `base/exporters/popeye/cronjob.yaml` | CronJob: initContainers popeye + python ANSI strip, main aws-cli upload |
| `base/exporters/k8sgpt/cronjob.yaml` | CronJob: initContainer curl K8s API, main aws-cli upload |
| `base/hub/normalizer/script-configmap.yaml` | normalize.py: boto3 читает S3, embed, upsert Qdrant |
| `base/hub/embedding-svc/embedding-svc.yaml` | Deployment sentence-transformers + Service :7997 |
| `base/hub/holmesgpt-toolset/kb-stack-toolset.yaml` | Toolset YAML + kb_tools.py для HolmesGPT |
| `overlays/hub/cluster-config.yaml` | ConfigMap с S3 endpoint, CLUSTER_ID=hub, Qdrant/embedding endpoints |
| `overlays/spoke-a/cluster-config.yaml` | ConfigMap с S3 endpoint, CLUSTER_ID=spoke-a |
| `applications/hub-sre-rag.yaml` | ArgoCD Application для Hub kustomize overlay |
| `applications/spoke-a-sre-rag.yaml` | ArgoCD Application для SpokeA kustomize overlay |

---

## 3. Что создать в Corporate S3 вручную

### 3.1 Bucket

- **Имя bucket**: `sre-rag`
- **Region**: выбрать ближайший к кластерам
- **Versioning**: включить (для аудита и отката)
- **Lifecycle rule**: удалять объекты с prefix `raw/` старше 90 дней (опционально, для экономии)

### 3.2 Структура prefix'ов

Создавать не нужно (S3 создаёт prefix'ы автоматически при upload). Ожидаемая структура:

```
sre-rag/
├── raw/
│   ├── kubescape/{CLUSTER_ID}/{timestamp}/findings.json
│   ├── popeye/{CLUSTER_ID}/{timestamp}/report.json
│   ├── k8sgpt/{CLUSTER_ID}/{timestamp}/results.json
│   └── kubevious/{CLUSTER_ID}/{timestamp}/topology.json
└── normalized/
    └── docs/{CLUSTER_ID}/{timestamp}/docs.jsonl
```

Где `{CLUSTER_ID}` = `hub`, `spoke-a`, `spoke-b`, ...

### 3.3 IAM пользователи

**Пользователь 1: `sre-rag-exporter`** — используется exporters на ВСЕХ кластерах (spoke и hub)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::sre-rag/raw/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::sre-rag",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["raw/*"]
        }
      }
    }
  ]
}
```

**Пользователь 2: `sre-rag-normalizer`** — используется normalizer и HolmesGPT на Hub

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::sre-rag",
        "arn:aws:s3:::sre-rag/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::sre-rag/normalized/*"
      ]
    }
  ]
}
```

### 3.4 Рекомендации по безопасности

- `sre-rag-exporter` имеет ТОЛЬКО право на запись в `raw/` — при компрометации spoke-кластера нельзя прочитать или удалить данные
- `sre-rag-normalizer` имеет право чтения всего bucket + запись в `normalized/`
- **НЕ давать** `s3:DeleteObject` ни одному из пользователей
- Включить Server-Side Encryption (SSE-S3 или SSE-KMS)
- Включить Access Logging для bucket

---

## 4. Hub кластер — компоненты

### 4.1 Список компонентов

| Компонент | Тип | Namespace | Источник |
|-----------|-----|-----------|----------|
| kubescape-exporter | CronJob | sre-exporters | overlays/hub |
| popeye-exporter | CronJob | sre-exporters | overlays/hub |
| k8sgpt-exporter | CronJob | sre-exporters | overlays/hub |
| embedding-svc | Deployment | sre-system | overlays/hub |
| normalizer | CronJob | sre-system | overlays/hub |
| Qdrant | Helm chart | qdrant | hub-qdrant.yaml |
| HolmesGPT | Helm chart | holmesgpt | hub-holmesgpt.yaml |
| HolmesGPT configs (toolset) | Kustomize | holmesgpt | hub-holmesgpt-configs.yaml |

**Не устанавливать на Hub:** MinIO (удалён), NetworkPolicy (не используются).

### 4.2 ArgoCD Application specs

**applications/hub-sre-rag.yaml** — основной kustomize (exporters + hub):
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: hub-sre-rag
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/agud97/sre-rag.git
    targetRevision: HEAD
    path: overlays/hub
  destination:
    server: https://kubernetes.default.svc
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      name: s3-credentials
      jsonPointers: [/data, /stringData]
    - group: ""
      kind: Secret
      name: s3-credentials-normalizer
      jsonPointers: [/data, /stringData]
```

**applications/hub-qdrant.yaml** — Qdrant Helm:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: qdrant
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://qdrant.github.io/qdrant-helm
    chart: qdrant
    targetRevision: "0.10.1"
    helm:
      values: |
        replicaCount: 1
        persistence:
          size: 5Gi
          storageClassName: openebs-hostpath
        service:
          type: ClusterIP
  destination:
    server: https://kubernetes.default.svc
    namespace: qdrant
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

**applications/hub-holmesgpt.yaml** — HolmesGPT Helm:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: holmesgpt
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://robusta-charts.storage.googleapis.com
    chart: holmes
    targetRevision: "0.19.0"
    helm:
      values: |
        additionalEnvVars:
          - name: MODEL
            value: "openai/qwen3-coder-30b-a3b-instruct-mlx"
          - name: OPENAI_API_BASE
            value: "http://llm-proxy.llm-proxy.svc.cluster.local:8080/v1"
          - name: OPENAI_API_KEY
            value: "not-needed"
          - name: AWS_ENDPOINT_URL
            valueFrom:
              configMapKeyRef:
                name: sre-rag-config
                key: S3_ENDPOINT
          - name: AWS_ACCESS_KEY_ID
            valueFrom:
              secretKeyRef:
                name: s3-credentials-normalizer
                key: accessKeyId
          - name: AWS_SECRET_ACCESS_KEY
            valueFrom:
              secretKeyRef:
                name: s3-credentials-normalizer
                key: secretAccessKey
          - name: S3_BUCKET
            valueFrom:
              configMapKeyRef:
                name: sre-rag-config
                key: S3_BUCKET
        toolsets:
          kubernetes/core:
            enabled: true
          kubernetes/logs:
            enabled: true
          prometheus/metrics:
            enabled: true
            config:
              prometheus_url: "http://vmsingle-vm-k8s-stack-victoria-metrics-k8s-stack.monitoring.svc:8429"
          runbook:
            enabled: true
          bash:
            enabled: true
          kb/stack:
            enabled: true
        additionalVolumes:
          - name: kb-stack-toolset
            configMap:
              name: kb-stack-toolset
        additionalVolumeMounts:
          - name: kb-stack-toolset
            mountPath: /app/holmes/plugins/toolsets/kb-stack-toolset.yaml
            subPath: kb-stack-toolset.yaml
          - name: kb-stack-toolset
            mountPath: /kb-scripts/kb_tools.py
            subPath: kb_tools.py
        resources:
          requests:
            memory: "2048Mi"
            cpu: "500m"
          limits:
            memory: "4096Mi"
            cpu: "2000m"
  destination:
    server: https://kubernetes.default.svc
    namespace: holmesgpt
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

**applications/hub-holmesgpt-configs.yaml** — ConfigMaps для HolmesGPT:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: holmesgpt-configs
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/agud97/sre-rag.git
    targetRevision: HEAD
    path: base/hub/holmesgpt-toolset
  destination:
    server: https://kubernetes.default.svc
    namespace: holmesgpt
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### 4.3 Как применить ArgoCD Applications на Hub

ArgoCD в Hub уже управляет idp-app-v1 apps. Новые Applications из sre-rag применяются вручную один раз:

```bash
export KUBECONFIG=/root/proj/cross/kubeconfig_6005021
kubectl apply -f applications/hub-sre-rag.yaml
kubectl apply -f applications/hub-qdrant.yaml          # пропустить если Qdrant уже работает
kubectl apply -f applications/hub-holmesgpt-configs.yaml
kubectl apply -f applications/hub-holmesgpt.yaml        # пропустить если HolmesGPT уже работает
```

---

## 5. SpokeA кластер — компоненты

### 5.1 Список компонентов

| Компонент | Тип | Namespace | Примечание |
|-----------|-----|-----------|-----------|
| kubescape-exporter | CronJob | sre-exporters | scan + upload to S3 |
| popeye-exporter | CronJob | sre-exporters | lint + upload to S3 |
| k8sgpt-exporter | CronJob | sre-exporters | collect CRDs + upload to S3 |
| RBAC | ClusterRole/Binding | - | readonly для exporters |
| sre-rag-config | ConfigMap | sre-exporters | CLUSTER_ID=spoke-a, S3 endpoint |
| s3-credentials | Secret | sre-exporters | exporter credentials (создать вручную) |

**НЕ разворачиваются на SpokeA:** Qdrant, embedding-svc, normalizer, HolmesGPT.

### 5.2 ArgoCD Application spec

**applications/spoke-a-sre-rag.yaml** — применяется в ArgoCD SpokeA:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: spoke-a-sre-rag
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/agud97/sre-rag.git
    targetRevision: HEAD
    path: overlays/spoke-a
  destination:
    server: https://kubernetes.default.svc
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      name: s3-credentials
      jsonPointers: [/data, /stringData]
```

### 5.3 Предварительные требования на SpokeA

1. ArgoCD установлен и работает ✅ (уже есть)
2. k8sgpt-operator: если **не установлен** — убрать k8sgpt из `overlays/spoke-a/kustomization.yaml`
3. Secret `s3-credentials` создан вручную в `sre-exporters` (см. раздел 7.2)

---

## 6. Изменения в коде относительно idp-app-v1

### 6.1 Uploader: minio/mc → amazon/aws-cli

Применяется ко ВСЕМ 4 exporter CronJobs (kubescape, popeye, k8sgpt, kubevious).

**Было:**
```yaml
containers:
  - name: uploader
    image: minio/mc:RELEASE.2025-08-13T08-35-41Z-cpuv1
    env:
      - name: MINIO_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: minio-credentials
            key: accessKey
      - name: MINIO_SECRET_KEY
        valueFrom:
          secretKeyRef:
            name: minio-credentials
            key: secretKey
    command:
      - /bin/sh
      - -c
      - |
        mc alias set local "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
        mc mb -p "local/kb-artifacts" || true
        mc cp "/tmp/kubescape-findings.json" \
          "local/kb-artifacts/raw/kubescape/${CLUSTER_ID}/${ts}/findings.json"
```

**Стало:**
```yaml
containers:
  - name: uploader
    image: amazon/aws-cli:2.15.40
    envFrom:
      - configMapRef:
          name: sre-rag-config        # содержит S3_ENDPOINT, S3_BUCKET, CLUSTER_ID
    env:
      - name: AWS_ACCESS_KEY_ID
        valueFrom:
          secretKeyRef:
            name: s3-credentials
            key: accessKeyId
      - name: AWS_SECRET_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: s3-credentials
            key: secretAccessKey
    command:
      - /bin/sh
      - -c
      - |
        set -euo pipefail
        ts=$(date -u +"%Y%m%dT%H%M%SZ")
        aws s3 cp "/tmp/kubescape-findings.json" \
          "s3://${S3_BUCKET}/raw/kubescape/${CLUSTER_ID}/${ts}/findings.json" \
          --endpoint-url "${S3_ENDPOINT}"
```

Для других exporters — аналогично, меняется только путь к файлу и prefix в S3:
- popeye: `/tmp/report.json` → `s3://${S3_BUCKET}/raw/popeye/${CLUSTER_ID}/${ts}/report.json`
- k8sgpt: `/shared/results.json` → `s3://${S3_BUCKET}/raw/k8sgpt/${CLUSTER_ID}/${ts}/results.json`
- kubevious: `/tmp/topology.json` → `s3://${S3_BUCKET}/raw/kubevious/${CLUSTER_ID}/${ts}/topology.json`

### 6.2 ConfigMap: kb-stack-config → sre-rag-config

**Hub overlay** (`overlays/hub/cluster-config.yaml`):
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sre-rag-config
  namespace: sre-exporters
data:
  CLUSTER_ID: "hub"
  S3_ENDPOINT: "https://s3.example.com"   # реальный endpoint corporate S3
  S3_BUCKET: "sre-rag"
  S3_REGION: "ru-central1"
  QDRANT_ENDPOINT: "http://qdrant.qdrant.svc.cluster.local:6333"
  EMBEDDING_ENDPOINT: "http://embedding-svc.sre-system.svc:7997"
```

**SpokeA overlay** (`overlays/spoke-a/cluster-config.yaml`) — только то, что нужно exporters:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sre-rag-config
  namespace: sre-exporters
data:
  CLUSTER_ID: "spoke-a"
  S3_ENDPOINT: "https://s3.example.com"
  S3_BUCKET: "sre-rag"
  S3_REGION: "ru-central1"
```

### 6.3 Secret: minio-credentials → s3-credentials

| Было | Стало |
|------|-------|
| Secret `minio-credentials` | Secret `s3-credentials` |
| key: `accessKey` | key: `accessKeyId` |
| key: `secretKey` | key: `secretAccessKey` |
| namespace: `kb-system` | namespace: `sre-exporters` |

На Hub дополнительно создаётся `s3-credentials-normalizer` в `sre-system` (и в `holmesgpt`) с normalizer credentials.

### 6.4 normalize.py — изменения S3 клиента

**Было:**
```python
minio_endpoint = os.environ["MINIO_ENDPOINT"]
access_key = os.environ["MINIO_ACCESS_KEY"]
secret_key = os.environ["MINIO_SECRET_KEY"]

s3 = boto3.client(
    "s3",
    endpoint_url=minio_endpoint,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name="us-east-1",
)
# ...
s3.get_paginator('list_objects_v2').paginate(Bucket="kb-artifacts", ...)
```

**Стало:**
```python
s3_endpoint = os.environ.get("S3_ENDPOINT", "")
s3_region = os.environ.get("S3_REGION", "us-east-1")
s3_bucket = os.environ.get("S3_BUCKET", "sre-rag")

# AWS_ACCESS_KEY_ID и AWS_SECRET_ACCESS_KEY подхватываются boto3 автоматически из env
kwargs = {"region_name": s3_region}
if s3_endpoint:
    kwargs["endpoint_url"] = s3_endpoint

s3 = boto3.client("s3", **kwargs)
# ...
s3.get_paginator('list_objects_v2').paginate(Bucket=s3_bucket, ...)
```

**Normalizer CronJob env vars:**
```yaml
env:
  - name: AWS_ACCESS_KEY_ID
    valueFrom:
      secretKeyRef:
        name: s3-credentials-normalizer
        key: accessKeyId
  - name: AWS_SECRET_ACCESS_KEY
    valueFrom:
      secretKeyRef:
        name: s3-credentials-normalizer
        key: secretAccessKey
envFrom:
  - configMapRef:
      name: sre-rag-config   # содержит S3_ENDPOINT, S3_BUCKET, S3_REGION, QDRANT_ENDPOINT, EMBEDDING_ENDPOINT
```

### 6.5 kb_tools.py — изменения S3 клиента

**Было (cmd_fetch):**
```python
endpoint = os.environ.get("MINIO_ENDPOINT", "http://minio.kb-system.svc:9000")
access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
s3 = boto3.client("s3",
    endpoint_url=endpoint,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name="us-east-1")
body = s3.get_object(Bucket="kb-artifacts", Key=path)["Body"].read()
```

**Стало:**
```python
s3_endpoint = os.environ.get("AWS_ENDPOINT_URL", "")
s3_region = os.environ.get("S3_REGION", "us-east-1")
bucket = os.environ.get("S3_BUCKET", "sre-rag")

kwargs = {"region_name": s3_region}
if s3_endpoint:
    kwargs["endpoint_url"] = s3_endpoint
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY — из env (прокидываются через HolmesGPT helm values)
s3 = boto3.client("s3", **kwargs)
body = s3.get_object(Bucket=bucket, Key=path)["Body"].read()
```

### 6.6 Убрано полностью (не переносится в sre-rag)

- `base/minio/` — весь MinIO (Deployment, PVC, Service, bucket-job)
- `base/networkpolicy/` — все NetworkPolicy (не используются)
- `base/kubevious/` — kubevious-exporter (опциональный, зависит от наличия Kubevious в кластере)

### 6.7 Namespace изменения

| idp-app-v1 | sre-rag Hub | sre-rag SpokeA |
|------------|-------------|----------------|
| `kb-system` | `sre-exporters` (CronJobs) + `sre-system` (Deployment) | `sre-exporters` |

---

## 7. Секреты — как передавать credentials

### Решение: Manual Secrets + ArgoCD ignoreDifferences

Простейший подход без дополнительных зависимостей. ArgoCD не перезаписывает секреты благодаря `ignoreDifferences`. В git хранятся пустые Secret-заглушки (`data: {}`).

### 7.1 Hub кластер (KUBECONFIG=/root/proj/cross/kubeconfig_6005021)

```bash
export KUBECONFIG=/root/proj/cross/kubeconfig_6005021

# Namespace создастся через ArgoCD, но можно создать заранее
kubectl create namespace sre-exporters --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace sre-system --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace holmesgpt --dry-run=client -o yaml | kubectl apply -f -

# Secret для exporters (namespace sre-exporters)
kubectl create secret generic s3-credentials \
  --namespace sre-exporters \
  --from-literal=accessKeyId='<EXPORTER_ACCESS_KEY_ID>' \
  --from-literal=secretAccessKey='<EXPORTER_SECRET_ACCESS_KEY>'

# Secret для normalizer (namespace sre-system)
kubectl create secret generic s3-credentials-normalizer \
  --namespace sre-system \
  --from-literal=accessKeyId='<NORMALIZER_ACCESS_KEY_ID>' \
  --from-literal=secretAccessKey='<NORMALIZER_SECRET_ACCESS_KEY>'

# Secret для HolmesGPT (namespace holmesgpt)
kubectl create secret generic s3-credentials-normalizer \
  --namespace holmesgpt \
  --from-literal=accessKeyId='<NORMALIZER_ACCESS_KEY_ID>' \
  --from-literal=secretAccessKey='<NORMALIZER_SECRET_ACCESS_KEY>'
```

### 7.2 SpokeA кластер (KUBECONFIG=/root/codex/kubeconfig_6144665)

```bash
export KUBECONFIG=/root/codex/kubeconfig_6144665

kubectl create namespace sre-exporters --dry-run=client -o yaml | kubectl apply -f -

# Используется тот же exporter ключ (PutObject only на raw/*)
kubectl create secret generic s3-credentials \
  --namespace sre-exporters \
  --from-literal=accessKeyId='<EXPORTER_ACCESS_KEY_ID>' \
  --from-literal=secretAccessKey='<EXPORTER_SECRET_ACCESS_KEY>'
```

### 7.3 Git-заглушки для Secret

В git хранить пустые заглушки (ArgoCD создаёт их, но данные не затирает):

```yaml
# base/exporters/rbac/secrets-stub.yaml
apiVersion: v1
kind: Secret
metadata:
  name: s3-credentials
  namespace: sre-exporters
type: Opaque
data: {}
```

---

## 8. Порядок реализации (пошагово)

### Фаза 0: Подготовка S3 (ручная, ~30 мин)

1. Создать bucket `sre-rag` в corporate S3
2. Создать IAM пользователя `sre-rag-exporter` с политикой из раздела 3.3
3. Создать IAM пользователя `sre-rag-normalizer` с политикой из раздела 3.3
4. Сохранить access key / secret key обоих пользователей
5. Проверить доступность S3 endpoint (curl или aws cli):
   ```bash
   AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> \
     aws s3 ls s3://sre-rag/ --endpoint-url <S3_ENDPOINT>
   ```

### Фаза 1: Создать структуру репозитория (~1-2 часа)

6. Создать директории согласно разделу 2
7. **base/exporters**: скопировать и адаптировать из idp-app-v1:
   - `namespace.yaml` (name: sre-exporters)
   - `rbac/serviceaccounts.yaml` (namespace: sre-exporters)
   - `rbac/roles.yaml` (ClusterRole kb-readonly + bindings)
   - `kubescape/cronjob.yaml` (заменить uploader на aws-cli)
   - `popeye/cronjob.yaml` (заменить uploader на aws-cli)
   - `k8sgpt/cronjob.yaml` + `rbac.yaml` (заменить uploader на aws-cli)
   - Все `kustomization.yaml`
8. **base/hub**: скопировать и адаптировать из idp-app-v1:
   - `namespace.yaml` (name: sre-system)
   - `embedding-svc/embedding-svc.yaml` (namespace: sre-system)
   - `normalizer/script-configmap.yaml` (normalize.py с новым S3 клиентом)
   - `normalizer/cronjob.yaml` (env vars: AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)
   - `holmesgpt-toolset/kb-stack-toolset.yaml` (kb_tools.py с новым S3 клиентом)
   - Все `kustomization.yaml`
9. **overlays/hub/**: `cluster-config.yaml` + `kustomization.yaml`
10. **overlays/spoke-a/**: `cluster-config.yaml` + `kustomization.yaml`
11. **applications/**: все 5 файлов из раздела 4 и 5
12. Push в git:
    ```bash
    cd /root/sre-rag
    git add .
    git commit -m "Initial multi-cluster sre-rag implementation"
    git push origin main
    ```

### Фаза 2: Деплой Hub (~30 мин)

```bash
export KUBECONFIG=/root/proj/cross/kubeconfig_6005021
```

13. Создать секреты (раздел 7.1)
14. Применить ArgoCD Applications:
    ```bash
    cd /root/sre-rag
    kubectl apply -f applications/hub-sre-rag.yaml
    kubectl apply -f applications/hub-holmesgpt-configs.yaml
    # hub-qdrant.yaml и hub-holmesgpt.yaml — пропустить если уже работают из idp-app-v1
    ```
15. Дождаться sync:
    ```bash
    kubectl get app hub-sre-rag -n argocd -w
    ```
16. Проверить поды:
    ```bash
    kubectl get cronjobs -n sre-exporters
    kubectl get deploy,svc -n sre-system
    ```

### Фаза 3: Деплой SpokeA (~15 мин)

```bash
export KUBECONFIG=/root/codex/kubeconfig_6144665
```

17. Создать секрет (раздел 7.2)
18. Применить ArgoCD Application:
    ```bash
    cd /root/sre-rag
    kubectl apply -f applications/spoke-a-sre-rag.yaml
    ```
19. Дождаться sync и проверить:
    ```bash
    kubectl get app spoke-a-sre-rag -n argocd
    kubectl get cronjobs -n sre-exporters
    ```

### Фаза 4: Валидация end-to-end (~30 мин)

20. Запустить exporter вручную на SpokeA:
    ```bash
    kubectl create job test-ks --from=cronjob/kubescape-exporter -n sre-exporters
    kubectl wait --for=condition=complete job/test-ks -n sre-exporters --timeout=300s
    kubectl logs job/test-ks -n sre-exporters -c uploader
    ```
21. Проверить данные в S3:
    ```bash
    aws s3 ls s3://sre-rag/raw/kubescape/spoke-a/ --endpoint-url <S3_ENDPOINT> --recursive
    ```
22. Запустить normalizer на Hub:
    ```bash
    export KUBECONFIG=/root/proj/cross/kubeconfig_6005021
    kubectl create job test-norm --from=cronjob/normalizer -n sre-system
    kubectl wait --for=condition=complete job/test-norm -n sre-system --timeout=300s
    kubectl logs job/test-norm -n sre-system
    ```
23. Проверить Qdrant:
    ```bash
    kubectl port-forward svc/qdrant 6333:6333 -n qdrant &
    curl -s http://localhost:6333/collections | python3 -c "import sys,json; [print(c['name']) for c in json.load(sys.stdin)['result']['collections']]"
    # Ожидается: kb_docs_hub, kb_docs_spoke-a
    ```
24. Проверить HolmesGPT:
    ```bash
    HOLMES_POD=$(kubectl get pod -n holmesgpt -l app.kubernetes.io/name=holmes -o jsonpath='{.items[0].metadata.name}')
    kubectl exec -n holmesgpt $HOLMES_POD -- \
      python3 /kb-scripts/kb_tools.py search "security findings" 5 spoke-a
    ```

---

## 9. Добавление нового Spoke кластера

### Чеклист: добавить SpokeB

- [ ] **1. Overlay**: Скопировать `overlays/spoke-a/` → `overlays/spoke-b/`
- [ ] **2. CLUSTER_ID**: В `overlays/spoke-b/cluster-config.yaml` заменить `CLUSTER_ID: spoke-a` → `CLUSTER_ID: spoke-b`
- [ ] **3. kustomization.yaml**: Убрать k8sgpt если k8sgpt-operator не установлен на SpokeB
- [ ] **4. ArgoCD Application**: Создать `applications/spoke-b-sre-rag.yaml`:
  ```yaml
  # Скопировать spoke-a-sre-rag.yaml, заменить:
  #   name: spoke-b-sre-rag
  #   path: overlays/spoke-b
  ```
- [ ] **5. Git push**: `git add . && git commit -m "Add spoke-b cluster" && git push`
- [ ] **6. Секрет**: На SpokeB кластере:
  ```bash
  kubectl create namespace sre-exporters
  kubectl create secret generic s3-credentials \
    --namespace sre-exporters \
    --from-literal=accessKeyId='<EXPORTER_ACCESS_KEY_ID>' \
    --from-literal=secretAccessKey='<EXPORTER_SECRET_ACCESS_KEY>'
  ```
- [ ] **7. ArgoCD Application**: На SpokeB:
  ```bash
  kubectl apply -f applications/spoke-b-sre-rag.yaml
  ```
- [ ] **8. Qdrant**: Коллекция `kb_docs_spoke-b` создастся автоматически при первом запуске normalizer (Hub обрабатывает все cluster_id из S3 `raw/`)
- [ ] **9. Проверка**: Запустить exporter вручную → проверить S3 → запустить normalizer → проверить Qdrant

**Normalizer** итерирует все prefix'ы в `raw/` и создаёт Qdrant коллекцию для каждого нового CLUSTER_ID автоматически.

---

## 10. Проверка работоспособности

### 10.1 S3 (ручная проверка credentials)

```bash
# Exporter: только write
AWS_ACCESS_KEY_ID=<exporter_key> AWS_SECRET_ACCESS_KEY=<exporter_secret> \
  aws s3 cp /dev/null s3://sre-rag/raw/test/test.txt --endpoint-url <S3_ENDPOINT>
# Ожидается: upload: /dev/null to s3://sre-rag/raw/test/test.txt

# Normalizer: read + write normalized/
AWS_ACCESS_KEY_ID=<normalizer_key> AWS_SECRET_ACCESS_KEY=<normalizer_secret> \
  aws s3 ls s3://sre-rag/raw/ --endpoint-url <S3_ENDPOINT>
# Ожидается: список файлов
```

### 10.2 После деплоя Hub

```bash
export KUBECONFIG=/root/proj/cross/kubeconfig_6005021

# ArgoCD sync
kubectl get app hub-sre-rag -n argocd
# Ожидается: Synced / Healthy

# CronJobs созданы
kubectl get cronjobs -n sre-exporters
# Ожидается: kubescape-exporter, popeye, k8sgpt-exporter

# embedding-svc работает
kubectl get deploy -n sre-system
kubectl run emb-test --rm -i --restart=Never --image=curlimages/curl \
  --command -- curl -s http://embedding-svc.sre-system.svc:7997/health
# Ожидается: {"status": "ok", "vector_size": 384}
```

### 10.3 После деплоя SpokeA

```bash
export KUBECONFIG=/root/codex/kubeconfig_6144665

kubectl get app spoke-a-sre-rag -n argocd
# Ожидается: Synced / Healthy

kubectl get cronjobs -n sre-exporters
# Ожидается: kubescape-exporter, popeye, k8sgpt-exporter

# Ручной запуск kubescape
kubectl create job test-ks --from=cronjob/kubescape-exporter -n sre-exporters
kubectl wait --for=condition=complete job/test-ks -n sre-exporters --timeout=300s
kubectl logs job/test-ks -n sre-exporters -c uploader
# Ожидается: upload: ... to s3://sre-rag/raw/kubescape/spoke-a/...
```

### 10.4 Normalizer end-to-end

```bash
export KUBECONFIG=/root/proj/cross/kubeconfig_6005021

kubectl create job test-norm --from=cronjob/normalizer -n sre-system
kubectl wait --for=condition=complete job/test-norm -n sre-system --timeout=300s
kubectl logs job/test-norm -n sre-system | grep -v "Downloading\|━\|Collecting"
# Ожидается: "Loaded N docs from spoke-a", "Upserted N to kb_docs_spoke-a"

# Qdrant коллекции
kubectl port-forward svc/qdrant 6333:6333 -n qdrant &
curl -s http://localhost:6333/collections | python3 -c \
  "import sys,json; [print(c['name']) for c in json.load(sys.stdin)['result']['collections']]"
# Ожидается: kb_docs_hub, kb_docs_spoke-a

curl -s http://localhost:6333/collections/kb_docs_spoke-a | \
  python3 -c "import sys,json; r=json.load(sys.stdin)['result']; print(f'points={r[\"points_count\"]} size={r[\"config\"][\"params\"][\"vectors\"][\"size\"]}')"
# Ожидается: points=N size=384
```

### 10.5 HolmesGPT kb/stack toolset

```bash
export KUBECONFIG=/root/proj/cross/kubeconfig_6005021

HOLMES_POD=$(kubectl get pod -n holmesgpt -l app.kubernetes.io/name=holmes \
  -o jsonpath='{.items[0].metadata.name}')

# Проверить что toolset загружен
kubectl logs -n holmesgpt $HOLMES_POD | grep "Toolset kb"
# Ожидается: ✅ Toolset kb/stack

# Прямой тест инструментов
kubectl exec -n holmesgpt $HOLMES_POD -- \
  python3 /kb-scripts/kb_tools.py search "security findings" 5 spoke-a
# Ожидается: [score=0.5xx] doc_type=finding_kubescape ...

# Тест через API
kubectl exec -n holmesgpt $HOLMES_POD -- python3 -c "
import urllib.request, json
req = urllib.request.Request(
    'http://localhost:5050/api/chat',
    data=json.dumps({'ask': 'What kubescape security findings exist for cluster spoke-a?'}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST'
)
with urllib.request.urlopen(req, timeout=300) as r:
    print(json.loads(r.read())['analysis'])
"
```
