# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 使用說明

當使用者詢問「這個環境怎麼用？」、「有哪些功能？」、「可以做什麼？」等問題時，請讀取 `GUIDE.md` 並以友善的方式呈現其內容。

## Project Overview

LaDeco (Landscape Decoration) is a landscape image semantic segmentation tool based on the OneFormer model (ADE20K dataset). It maps ADE20K's 150 classes into a custom 4-level hierarchical label system (L1: nature/man_made → L2 → L3 → L4: ~50 fine-grained categories) and computes area ratios plus a Natural Feature Index (LC_NFI).

Reference: Li-Chih Ho (2023), *LaDeco: A Tool to Analyze Visual Landscape Elements*, Ecological Informatics, vol. 78.

## Build & Run

```bash
# Build Docker image
docker build -t lclab/ladeco-internal:v0.0.1 -t lclab/ladeco-internal:latest .

# Run with GPU and NAS mount
docker run --rm -ti --gpus all -v /path/to/datasets:/mnt/ai_data -p 127.0.0.1:8000:8000 lclab/ladeco-internal

# Run via Docker Compose (reads .env for HOST_IP, HOST_PORT, DATABASES_ROOT)
docker compose up

# Run locally without Docker (requires CUDA-capable GPU or will fall back to CPU)
pip install -r requirements.txt
python server.py  # serves on http://127.0.0.1:8000

# Run MCP server (stdio, for Claude Code)
python mcp_server.py
```

## Deployment

兩個服務皆部署在同一 K8s cluster (MicroK8s)。

- NFS server：`192.168.1.152:/volume1/ai_data` → mount 至 `/mnt/ai_data`
- Namespace：`ladeco`
- K8s 配置：`k8s/` 目錄，透過 `kustomization.yaml` 管理

| 服務 | Image | NodePort | GPU |
|------|-------|----------|-----|
| LaDeco | `localhost:32000/ladeco-internal:latest` | `30800` | 1× NVIDIA |
| NAS File Server | `192.168.1.152:5679/nas-files:latest` | `30803` | — |

### 基礎設施

| 角色 | Host / SSH alias | IP | SSH Port | 說明 |
|------|------------------|------|----------|------|
| GitLab Server | nas02 | 192.168.1.152 | 52500 | GitLab (port 8929) |
| Docker Registry | — | 192.168.1.152:5679 | — | Docker Registry v2 (HTTP) |
| GitLab Runner | ub3 | 192.168.1.157 | 52522 | shell executor，`gitlab-runner` 用戶需在 docker group |
| K8s Node | ub6-ai02 | 192.168.1.162 | 52522 | MicroK8s 主節點 |
| K8s Node | ub5 | 140.128.121.52 | 52522 | |
| K8s Node | ub3 | 192.168.1.157 | 52522 | 同時是 Runner |
| K8s Node | labsl-dualgpu | 192.168.1.245 | 5250 | |

### GitLab CI/CD（NAS File Server）

`.gitlab-ci.yml` 定義 pipeline：GitLab push → Runner build image → push 到 NAS Registry → 手動觸發 deploy 到 K8s。

```bash
# Pipeline 自動觸發（push to GitLab）
git push gitlab main

# 驗證 Registry 有 image
curl http://192.168.1.152:5679/v2/nas-files/tags/list

# 驗證服務
curl http://192.168.1.162:30803/healthcheck
```

**insecure registry 配置**（所有 K8s node 皆需設定，因為 192.168.1.152:5679 是 HTTP）：

- **Docker daemon**（Runner ub3）：`/etc/docker/daemon.json` → `"insecure-registries": ["localhost:32000", "192.168.1.152:5679"]`
- **MicroK8s containerd**（所有 K8s node）：`/var/snap/microk8s/current/args/certs.d/192.168.1.152:5679/hosts.toml`
  ```toml
  server = "http://192.168.1.152:5679"
  [host."http://192.168.1.152:5679"]
    capabilities = ["pull", "resolve"]
    skip_verify = true
  ```

**Runner SSH deploy**：`gitlab-runner` 用戶的 SSH key (`~/.ssh/id_ed25519`) 已加入 K8s 主節點 (ub6-ai02) 的 `lichih` authorized_keys。CI 中以 `ssh -p 52522 lichih@192.168.1.162` 執行 kubectl。

### LaDeco (主服務)

```bash
# 1. 複製原始碼到 K8s 節點（根目錄下所有 .py + Dockerfile + requirements.txt）
scp -P 52522 {Dockerfile,requirements.txt,server.py,engine.py,core.py,service.py,mcp_server.py,api_server.py} \
  192.168.1.162:/tmp/ladeco-build/

# 2. Build 並 push
ssh -p 52522 192.168.1.162 "cd /tmp/ladeco-build && \
  docker build -t localhost:32000/ladeco-internal:latest . && \
  docker push localhost:32000/ladeco-internal:latest"

# 3. Rollout restart
ssh -p 52522 192.168.1.162 "microk8s kubectl rollout restart deployment/ladeco -n ladeco"

# 4. 驗證
curl http://192.168.1.162:30800/healthcheck
```

另有舊版部署工具（非 K8s）：
- **deploy.sh** — 首次安裝，建立 systemd service
- **ci_cd.sh** — `deploy`, `update`, `rollback`, `status`, `logs`
- **GitHub Actions** (`.github/workflows/deploy.yml`) — 手動觸發 → Docker Hub → SSH 部署

### NAS File Server

已改用 GitLab CI/CD 部署（見上方「GitLab CI/CD」段落），push 到 GitLab 即觸發 build，deploy 手動觸發。

手動部署（備用）：

```bash
# 1. Build 並 push 到 NAS Registry
docker build -t 192.168.1.152:5679/nas-files:latest -f nas-files/Dockerfile nas-files/
docker push 192.168.1.152:5679/nas-files:latest

# 2. Rollout restart
ssh -p 52522 192.168.1.162 "microk8s kubectl rollout restart deployment/nas-files -n ladeco"

# 3. 驗證
curl http://192.168.1.162:30803/healthcheck
```

## Architecture

Three-layer architecture:

```
┌──────────────────────────────────────────────┐
│  Interface Layer（介面層）                     │
│  ├── mcp_server.py      → Claude Code (MCP)  │
│  └── api_server.py      → REST API (FastAPI) │
├──────────────────────────────────────────────┤
│  Service Layer（服務層）                       │
│  └── service.py         → 業務邏輯            │
├──────────────────────────────────────────────┤
│  Core Layer（核心層）                          │
│  └── engine.py          → 模型推論            │
└──────────────────────────────────────────────┘

server.py  → 統一入口：掛載 REST API (/api) + MCP SSE (/mcp)
core.py    → 向後相容 shim (from engine import *)
```

**engine.py** — The `Ladeco` class loads `shi-labs/oneformer_ade20k_swin_large` and exposes `predict()`. Returns a `LadecoOutput` object with:
- `visualize(level)` → colored segmentation maps as matplotlib Figures
- `area()` → per-image dict of all label area ratios + `others` + `LC_NFI`
- `color_map(level)` / `color_legend(level)` → viridis-based coloring (available both on `Ladeco` and `LadecoOutput`)

Module-level `_build_color_map()` and `_build_color_legend()` are shared by both classes.

The label hierarchy is built bottom-up in `_get_ladeco_labels()`: L4 labels map to ADE20K indices, then L3/L2/L1 aggregate by tuple concatenation.

**service.py** — Business logic layer (model singleton, inference pipelines, CSV export, dataset listing, chart plotting). Key functions:
- `predict_batch(dataset, callback)` → `BatchResult` dataclass
- `predict_images(paths, callback)` → list of area dicts
- `visualize_image(path, level)` → (Figure, area_dict)
- `get_area(path, level)` → area dict (no visualization)
- `list_datasets()` / `preview_dataset(name)` → NAS dataset browsing
- `get_color_legend(level)` / `get_label_hierarchy()` → metadata
- `fig2img(fig)` / `plot_pie(data, colors)` → chart utilities

**api_server.py** — REST API endpoints (mounted at `/api` by server.py):
- `POST /predict` — single image area ratios (`?level=1-4`, default all)
- `POST /predict/batch` — batch NAS dataset
- `POST /visualize` — segmentation map (base64 PNG)
- `GET /datasets` — list NAS datasets
- `GET /datasets/{name}/preview` — preview dataset
- `GET /download/{filename}` — download CSV
- Swagger UI available at `/api/docs`

**mcp_server.py** — 9 MCP tools for Claude Code (stdio transport):
`predict`, `predict_batch`, `predict_images`, `visualize`, `get_area`, `list_datasets`, `preview_dataset`, `get_color_legend`, `get_label_hierarchy`

MCP tool behavior: `predict`, `predict_images`, `get_area` default to `level=2` (L2). Tool docstrings instruct Claude to ask the user which hierarchy level (L1–L4) they need before calling; if the user does not specify, use the default L2.

**server.py** — Unified entry point: mounts REST API at `/api`, MCP SSE at `/mcp`, healthcheck at `/healthcheck`.

### NAS File Server (`nas-files/`)

Same three-layer architecture, deployed as a separate container:

```
┌──────────────────────────────────────────────┐
│  Interface Layer（介面層）                     │
│  ├── mcp_server.py      → Claude Code (MCP)  │
│  └── api_server.py      → REST API (FastAPI) │
├──────────────────────────────────────────────┤
│  Service Layer（服務層）                       │
│  └── service.py         → 業務邏輯            │
└──────────────────────────────────────────────┘

server.py  → 統一入口：掛載 REST API (/api) + MCP SSE (/mcp)
```

**service.py** — Business logic for NAS file operations. All functions return Python objects (dict/list), not JSON strings. Key functions:
- `list_files(path, recursive)` → list of entry dicts
- `read_file(path, binary)` → text or base64 string
- `write_file(path, content, binary)` → status dict
- `delete_file(path)` / `move_file(src, dst)` / `copy_file(src, dst)` → status dict
- `file_info(path)` → metadata dict (size, timestamps, permissions)
- `search_files(pattern, path)` → list of matching relative paths
- `upload_files(directory, filenames, contents)` → list of status dicts (raw bytes, no base64)

Path security: `_safe_path()` resolves and validates all paths stay under `BASE_PATH`. `upload_files()` additionally sanitizes filenames via `os.path.basename()`.

**mcp_server.py** — 8 MCP tools (thin wrappers calling `service.*`, serializing with `json.dumps()`):
`list_files`, `read_file`, `write_file`, `delete_file`, `move_file`, `copy_file`, `file_info`, `search_files`

Supports `mount_mcp_sse(app)` for SSE integration and `--transport stdio|sse` for standalone use.

**api_server.py** — FastAPI REST endpoints (mounted at `/api` by server.py):
- `POST /upload/{directory:path}` — multipart multi-file upload (core feature, bypasses LLM)
- `GET /files` — list files (`?path=.&recursive=false`)
- `GET /files/info` — file/directory details (`?path=...`)
- `GET /files/search` — glob search (`?pattern=*.jpg&path=.`)
- `POST /files/write` — write file (JSON body)
- `DELETE /files` — delete file/empty dir (`?path=...`)
- `POST /files/move` / `POST /files/copy` — move/copy (JSON body)
- Global `ValueError` exception handler → HTTP 400
- Swagger UI at `/api/docs`

**server.py** — Unified entry point: mounts REST API at `/api`, MCP SSE at `/mcp`, healthcheck at `/healthcheck`.

```bash
# Build & run NAS file server
cd nas-files
docker build -t lclab/nas-files:latest .
docker run --rm -v /path/to/nas:/mnt/ai_data -p 8000:8000 lclab/nas-files

# Run MCP server standalone (stdio, for Claude Code)
python mcp_server.py

# Upload files directly (no LLM needed)
curl -X POST http://host:30803/api/upload/dataset_name \
  -F "files=@photo1.jpg" -F "files=@photo2.jpg"
```

## 區域網路服務總覽

### MCP 服務（Claude Code 可直接呼叫）

| 服務 | Transport | 設定方式 | 工具數 | 說明 |
|------|-----------|----------|--------|------|
| LaDeco | stdio | `.mcp.json` → `python mcp_server.py` | 9 | 景觀影像語意分割：`predict`, `predict_batch`, `predict_images`, `visualize`, `get_area`, `list_datasets`, `preview_dataset`, `get_color_legend`, `get_label_hierarchy` |
| NAS File Server | stdio | `.mcp.json` → `python nas-files/mcp_server.py` | 8 | NAS 檔案操作：`list_files`, `read_file`, `write_file`, `delete_file`, `move_file`, `copy_file`, `file_info`, `search_files` |

兩個服務也提供 SSE transport（掛載於各自 server.py 的 `/mcp` 路徑），供非 stdio 環境使用。

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

## Key Conventions

- NAS datasets mount at `/mnt/ai_data` (read-only in compose.yml)
- Temporary CSV results go to `/tmp/LaDeco-*.csv`, cleaned weekly by cron inside the container
- The Docker healthcheck pings `/healthcheck` every 15 minutes
- `.env` configures `HOST_IP`, `HOST_PORT`, `DATABASES_ROOT`, `COMPOSE_PROJECT_NAME`
- The project has no test suite or linter configured
- `core.py` is a backward-compatibility shim (`from engine import *`)
