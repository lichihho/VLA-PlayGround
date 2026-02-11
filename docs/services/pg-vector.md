# pg-vector — 研究資料庫 + 向量搜尋

## Overview

PostgreSQL + pgvector 資料庫，管理研究專案、影像中繼資料、分析結果，並支援向量相似度搜尋（以圖搜圖）。

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
│  Data Layer（資料層）                          │
│  └── db.py              → PostgreSQL 連線管理  │
│  └── init.sql           → Schema 初始化       │
└──────────────────────────────────────────────┘

server.py  → 統一入口：掛載 REST API (/api) + MCP SSE (/mcp)
```

### Database Schema

```sql
-- projects
projects (project_id SERIAL PK, researcher_name, topic, created_at)

-- images (shared across projects)
images (image_id SERIAL PK, source_type, lat, lng, local_path,
        remote_url, checksum, embedding vector(512), created_at)
  → HNSW index on embedding (vector_cosine_ops)
  → UNIQUE index on checksum

-- analysis_results (links projects ↔ images)
analysis_results (result_id SERIAL PK, project_id FK, image_id FK,
                  tool_name, result_json JSONB, confidence, model_version, created_at)
  → CASCADE delete from projects
```

### service.py

Business logic for all CRUD and vector search. All functions return Python objects (dict/list), not JSON strings. Key functions:

**Projects:** `create_project`, `get_project`, `list_projects`, `update_project`, `delete_project`, `get_project_summary`, `get_project_images`

**Images:** `create_image`, `get_image`, `list_images`, `update_image_embedding`, `delete_image`

**Analysis Results:** `create_analysis_result`, `get_analysis_result`, `list_analysis_results`, `delete_analysis_result`

**Vector Search:** `search_similar_images(embedding, top_k, threshold)`, `search_similar_by_image_id(image_id, top_k, threshold)` — cosine similarity via `<=>` operator

### mcp_server.py

13 MCP tools (thin wrappers calling `service.*`, serializing with `json.dumps()`):
`create_project`, `get_project`, `list_projects`, `delete_project`, `create_image`, `get_image`, `list_images`, `update_image_embedding`, `create_analysis_result`, `list_analysis_results`, `search_similar_images`, `search_similar_by_image_id`, `get_project_summary`

Supports `mount_mcp_sse(app)` for SSE integration and `--transport stdio|sse` for standalone use.

### api_server.py

FastAPI REST endpoints (mounted at `/api` by server.py). See [REST API Reference](#rest-api-reference) below.

### server.py

Unified entry point: mounts REST API at `/api`, MCP SSE at `/mcp`, healthcheck at `/healthcheck`.

## Build & Run

```bash
# Build & run with Docker Compose (development)
cd pg-vector
docker compose up --build

# Run MCP server standalone (stdio, for Claude Code)
python mcp_server.py
```

## Deployment

使用 GitLab CI/CD 自動部署到 NAS02。`pg-vector/**` 變更 push 到 GitLab 後自動 build + deploy。詳見 [infrastructure.md](../infrastructure.md)。

| 項目 | 值 |
|------|---|
| Image | `192.168.1.152:5679/pg-vector:latest` |
| Port | `30805` |
| 部署主機 | NAS02 (192.168.1.152) |
| 部署方式 | Docker Compose |
| 部署路徑 | `/volume1/docker/pg-vector/` |
| CI/CD | `.gitlab-ci.yml`（VLA-PlayGround repo root） |

手動部署（備用）：

```bash
# 1. Build 並 push 到 NAS Registry
docker build -t 192.168.1.152:5679/pg-vector:latest -f pg-vector/Dockerfile pg-vector/
docker push 192.168.1.152:5679/pg-vector:latest

# 2. SSH 到 NAS02 部署
ssh -p 52500 lichih@192.168.1.152
cd /volume1/docker/pg-vector
export PATH=/usr/local/bin:$PATH
docker compose pull && docker compose up -d

# 3. 驗證
curl http://192.168.1.152:30805/healthcheck
```

---

## REST API Reference

Base URL: `http://<host>:<port>/api`

Swagger UI: `/api/docs`

### Projects

#### POST `/api/projects`

建立新研究專案。

**Request Body:**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `researcher_name` | `str` | 研究者名稱 |
| `topic` | `str` | 研究主題 |

#### GET `/api/projects`

列出所有研究專案。

#### GET `/api/projects/{project_id}`

取得指定專案。

#### PUT `/api/projects/{project_id}`

更新專案（可部分更新 `researcher_name`, `topic`）。

#### DELETE `/api/projects/{project_id}`

刪除專案（CASCADE 刪除相關 analysis_results）。

#### GET `/api/projects/{project_id}/summary`

取得專案摘要，包含 image_count、result_count、tools_used。

#### GET `/api/projects/{project_id}/images`

取得專案關聯的所有影像（透過 analysis_results 關聯）。

### Images

#### POST `/api/images`

註冊新影像。

**Request Body:**

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `source_type` | `str` | `"local"` | 來源類型（local, gsv, url） |
| `lat` | `float?` | — | 緯度 |
| `lng` | `float?` | — | 經度 |
| `local_path` | `str?` | — | NAS 上的檔案路徑 |
| `remote_url` | `str?` | — | 遠端 URL |
| `checksum` | `str?` | — | 檔案校驗碼（去重） |
| `embedding` | `float[512]?` | — | 512 維向量 |

#### GET `/api/images`

列出影像（分頁）。

**Query 參數:**

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `limit` | `int` | 50 | 上限 1–500 |
| `offset` | `int` | 0 | 跳過筆數 |

#### GET `/api/images/{image_id}`

取得指定影像。

#### PUT `/api/images/{image_id}/embedding`

更新影像的 embedding 向量。

**Request Body:**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `embedding` | `float[512]` | 512 維向量 |

#### DELETE `/api/images/{image_id}`

刪除影像。

### Analysis Results

#### POST `/api/results`

儲存分析結果（連結 project ↔ image）。

**Request Body:**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `project_id` | `int` | 專案 ID |
| `image_id` | `int` | 影像 ID |
| `tool_name` | `str` | 分析工具名稱 |
| `result_json` | `object?` | 分析結果 JSON |
| `confidence` | `float?` | 信心分數 0.0–1.0 |
| `model_version` | `str?` | 模型版本 |

#### GET `/api/results`

列出分析結果（可篩選）。

**Query 參數:**

| 參數 | 型別 | 說明 |
|---|---|---|
| `project_id` | `int?` | 篩選專案 |
| `image_id` | `int?` | 篩選影像 |
| `tool_name` | `str?` | 篩選工具 |
| `limit` | `int` | 上限 1–500（預設 50） |
| `offset` | `int` | 跳過筆數（預設 0） |

#### DELETE `/api/results/{result_id}`

刪除分析結果。

### Vector Search

#### POST `/api/search/similar`

以 embedding 向量搜尋相似影像。

**Request Body:**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `embedding` | `float[512]` | 查詢向量 |
| `top_k` | `int` | 回傳筆數（預設 10） |
| `threshold` | `float?` | 最低相似度 0.0–1.0 |

#### GET `/api/search/similar/{image_id}`

以指定影像搜尋相似影像。

**Query 參數:**

| 參數 | 型別 | 說明 |
|---|---|---|
| `top_k` | `int` | 回傳筆數（預設 10） |
| `threshold` | `float?` | 最低相似度 |

### GET `/healthcheck`

健康檢查端點（位於根路徑，非 `/api` 下）。回傳資料庫連線狀態。

### 錯誤處理

- Global `ValueError` exception handler → HTTP 400
- 所有錯誤以 JSON 格式回傳
