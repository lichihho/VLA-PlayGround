# 基礎設施總覽

## 叢集架構

```
┌─────────────────────────────────────────────────────────┐
│                    區域網路 192.168.1.x                   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │         Synology NAS (192.168.1.152)             │    │
│  │  - Docker Registry      :5679                    │    │
│  │  - GitLab CE             :8929 (HTTP)            │    │
│  │  - GitLab SSH            :2222                   │    │
│  │  - NFS: /volume1/ai_data → /mnt/ai_data         │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌───────────────── MicroK8s HA 叢集 ────────────────┐  │
│  │                                                    │  │
│  │  192.168.1.252  (master)  RTX 8000  62G RAM       │  │
│  │  192.168.1.162  (master)  RTX 8000  62G RAM       │  │
│  │  192.168.1.157  (master)  RTX 8000  62G RAM       │  │
│  │    └── GitLab Runner (lcl-ub3-runner)             │  │
│  │  192.168.1.245  (standby) 2x RTX 3090  125G RAM  │  │
│  │                                                    │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 主機清單

| 角色 | Host / SSH alias | IP | SSH Port | GPU | RAM | 說明 |
|------|------------------|------|----------|-----|-----|------|
| K8s master | — | 192.168.1.252 | — | RTX 8000 | 62G | 本機（開發機） |
| K8s master | ub6-ai02 | 192.168.1.162 | 52522 | RTX 8000 | 62G | MicroK8s 主節點 |
| K8s master / Runner | ub3 (lcl-ub3) | 192.168.1.157 | 52522 | RTX 8000 | 62G | 同時是 GitLab Runner |
| K8s standby | labsl-dualgpu | 192.168.1.245 | 5250 | 2× RTX 3090 | 125G | 內網 SSH port 與其他節點不同 |
| NAS / GitLab / Registry | nas02 (LCL-NAS-02) | 192.168.1.152 | 52500 | — | 31G | Synology NAS, Intel Xeon D-1527 |

> 192.168.1.245 外網 IP 為 140.128.121.226:52522（路由器 port forwarding）。

## K8s 服務部署

兩個服務皆部署在同一 K8s cluster (MicroK8s)。

- NFS server：`192.168.1.152:/volume1/ai_data` → mount 至 `/mnt/ai_data`
- Namespace：`ladeco`
- K8s 配置：`k8s/` 目錄，透過 `kustomization.yaml` 管理

| 服務 | Image | NodePort | GPU |
|------|-------|----------|-----|
| LaDeco | `localhost:32000/ladeco-internal:latest` | `30800` | 1× NVIDIA |
| NAS File Server | `192.168.1.152:5679/nas-files:latest` | `30803` | — |

---

## Image 建置與部署流程

### 流程圖

```
開發者 (VS Code / Claude Code)
   │
   │ git push
   ▼
GitLab (192.168.1.152:8929)
   │
   │ 觸發 CI/CD Pipeline
   ▼
GitLab Runner (192.168.1.157)
   │
   │ docker build & push
   ▼
Docker Registry (192.168.1.152:5679)
   │
   │ image pull (by K8s)
   ▼
MicroK8s 叢集 (252, 162, 157, 245)
```

### NAS File Server（GitLab CI/CD 自動化）

`.gitlab-ci.yml` 定義 pipeline：GitLab push → Runner build image → push 到 NAS Registry → 手動觸發 deploy 到 K8s。

```bash
# 1. Push 到 GitLab（自動觸發 CI build）
git push gitlab main

# 2. 驗證 Registry 有 image
curl http://192.168.1.152:5679/v2/nas-files/tags/list

# 3. 手動觸發 deploy（或在 GitLab UI 點 deploy stage）

# 4. 驗證服務
curl http://192.168.1.162:30803/healthcheck
```

### LaDeco（手動部署）

```bash
# 1. 複製原始碼到 K8s 節點
scp -P 52522 {Dockerfile,requirements.txt,server.py,engine.py,core.py,service.py,mcp_server.py,api_server.py} \
  192.168.1.162:/tmp/ladeco-build/

# 2. Build 並 push 到 MicroK8s 內建 Registry
ssh -p 52522 192.168.1.162 "cd /tmp/ladeco-build && \
  docker build -t localhost:32000/ladeco-internal:latest . && \
  docker push localhost:32000/ladeco-internal:latest"

# 3. Rollout restart
ssh -p 52522 192.168.1.162 "microk8s kubectl rollout restart deployment/ladeco -n ladeco"

# 4. 驗證
curl http://192.168.1.162:30800/healthcheck
```

### NAS File Server 手動部署（備用）

```bash
# 1. Build 並 push 到 NAS Registry
docker build -t 192.168.1.152:5679/nas-files:latest -f nas-files/Dockerfile nas-files/
docker push 192.168.1.152:5679/nas-files:latest

# 2. Rollout restart
ssh -p 52522 192.168.1.162 "microk8s kubectl rollout restart deployment/nas-files -n ladeco"

# 3. 驗證
curl http://192.168.1.162:30803/healthcheck
```

### LaDeco 舊版部署工具（非 K8s）

- **deploy.sh** — 首次安裝，建立 systemd service
- **ci_cd.sh** — `deploy`, `update`, `rollback`, `status`, `logs`
- **GitHub Actions** (`.github/workflows/deploy.yml`) — 手動觸發 → Docker Hub → SSH 部署

---

## GitLab CE

部署在 Synology NAS 上，作為團隊的 Git 倉庫和 CI/CD 平台。

| 項目 | 值 |
|------|---|
| 主機 | LCL-NAS-02 (192.168.1.152) |
| 平台 | Synology NAS, Docker |
| CPU | Intel Xeon D-1527 @ 2.20GHz, 8 核 |
| RAM | 31GB |
| 儲存 | /volume1（53TB 可用） |
| 網頁介面 | `http://192.168.1.152:8929` |
| Git SSH | `ssh://git@192.168.1.152:2222` |

### GitLab Docker Compose

部署位置：`192.168.1.152:/volume1/docker/gitlab/`

```yaml
version: '3.8'

services:
  gitlab:
    image: gitlab/gitlab-ce:latest
    container_name: gitlab
    restart: always
    hostname: gitlab.local
    environment:
      GITLAB_OMNIBUS_CONFIG: |
        external_url 'http://192.168.1.152:8929'
        gitlab_rails['time_zone'] = 'Asia/Taipei'
        gitlab_rails['gitlab_shell_ssh_port'] = 2222
        prometheus_monitoring['enable'] = false
        puma['worker_processes'] = 2
    ports:
      - '8929:8929'
      - '2222:22'
    volumes:
      - '/volume1/docker/gitlab/config:/etc/gitlab'
      - '/volume1/docker/gitlab/logs:/var/log/gitlab'
      - '/volume1/docker/gitlab/data:/var/opt/gitlab'
    shm_size: '256m'
```

| 設定 | 說明 |
|------|------|
| `external_url` | 使用 port 8929（避開 NAS 的 80/443） |
| `gitlab_shell_ssh_port` | 使用 port 2222（避開 NAS 的 SSH） |
| `prometheus_monitoring` | 關閉（節省 NAS 資源） |
| `puma['worker_processes']` | 設為 2（節省 RAM） |
| `restart: always` | NAS 重啟後自動恢復 |

---

## GitLab Runner

安裝在效能較好的節點（非 NAS），用於執行 CI/CD Pipeline。

| 項目 | 值 |
|------|---|
| 主機 | lcl-ub3 (192.168.1.157) |
| Runner 版本 | 18.8.0 |
| Executor | shell |
| Runner 名稱 | lcl-ub3-runner |
| Tags | `shell`, `gpu`, `build` |
| 接受未標記任務 | 是 |
| 設定檔 | `/etc/gitlab-runner/config.toml` |

Runner 透過 SSH 執行 K8s 部署：`gitlab-runner` 用戶的 SSH key (`~/.ssh/id_ed25519`) 已加入 K8s 主節點 (ub6-ai02) 的 `lichih` authorized_keys。CI 中以 `ssh -p 52522 lichih@192.168.1.162` 執行 kubectl。

### Runner 前置需求

- `gitlab-runner` 用戶需加入 docker group
- Docker daemon 需設定 insecure registry（見下方）

---

## Docker Registry 設定

### insecure registry 配置

因為 `192.168.1.152:5679` 是 HTTP，所有需要存取的節點皆需設定：

**Docker daemon**（Runner ub3）：

`/etc/docker/daemon.json`
```json
{
  "insecure-registries": ["localhost:32000", "192.168.1.152:5679"]
}
```

**MicroK8s containerd**（所有 K8s node）：

`/var/snap/microk8s/current/args/certs.d/192.168.1.152:5679/hosts.toml`
```toml
server = "http://192.168.1.152:5679"

[host."http://192.168.1.152:5679"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
```

### Registry 設定狀態

| 節點 | IP | containerd 設定 |
|------|------|-----------------|
| 本機 | 192.168.1.252 | 已設定 |
| ub6-ai02 | 192.168.1.162 | 已設定 |
| lcl-ub3 | 192.168.1.157 | 已設定 |
| labsl-dualgpu | 192.168.1.245 | 已設定 |

> containerd 動態讀取 `certs.d/` 目錄，不需要重啟服務即生效。

---

## SSH 設定

### 開發機 SSH Key

| 項目 | 說明 |
|------|------|
| Key 位置 | 本機 `~/.ssh/id_ed25519` |
| 類型 | Ed25519 |
| 已佈署至 | 192.168.1.162, 192.168.1.157, 192.168.1.245 |

### SSH 連線快速參考

```bash
# ub6-ai02（K8s 主節點）
ssh -p 52522 lichih@192.168.1.162

# lcl-ub3（Runner）
ssh -p 52522 lichih@192.168.1.157

# labsl-dualgpu（注意 port 不同）
ssh -p 5250 lichih@192.168.1.245
# 或透過外網
ssh -p 52522 lichih@140.128.121.226

# NAS
ssh -p 52500 lichih@192.168.1.152
```

---

## 區域網路服務總覽

### MCP 服務（Claude Code 可直接呼叫）

| 服務 | Transport | 設定方式 | 工具數 | 說明 |
|------|-----------|----------|--------|------|
| LaDeco | SSE | `.mcp.json` → `http://192.168.1.162:30800/mcp/sse` | 9 | 景觀影像語意分割 |
| NAS File Server | SSE | `.mcp.json` → `http://192.168.1.162:30803/mcp/sse` | 8 | NAS 檔案操作 |

兩個服務也支援 stdio transport（`python mcp_server.py`），供本機開發使用。

### REST API 服務

| 服務 | 端點 | Swagger UI | 健康檢查 | 說明 |
|------|------|------------|----------|------|
| LaDeco | `http://192.168.1.162:30800/api/` | `/api/docs` | `/healthcheck` | 影像推論、批次分析、視覺化、資料集管理 |
| NAS File Server | `http://192.168.1.162:30803/api/` | `/api/docs` | `/healthcheck` | 檔案 CRUD、搜尋、多檔上傳 |
| GitLab | `http://192.168.1.152:8929/api/v4/` | — | — | GitLab REST API（需 Personal Access Token） |
| Docker Registry | `http://192.168.1.152:5679/v2/` | — | — | Docker Registry v2 API（查詢/管理 image） |

### 服務存取範例

```bash
# LaDeco API
curl -X POST http://192.168.1.162:30800/api/predict -F "file=@photo.jpg"

# NAS File Server API
curl http://192.168.1.162:30803/api/files?path=.
curl -X POST http://192.168.1.162:30803/api/upload/dataset_name -F "files=@photo.jpg"

# GitLab API（需 token）
curl --header "PRIVATE-TOKEN: <token>" http://192.168.1.152:8929/api/v4/projects/3/pipelines

# Docker Registry API
curl http://192.168.1.152:5679/v2/_catalog
curl http://192.168.1.152:5679/v2/nas-files/tags/list
```
