# NAS File Server — 檔案管理服務

## Overview

操作 NAS 儲存設備上的資料集檔案，提供瀏覽、搜尋、CRUD、多檔上傳等功能。

## Architecture

Three-layer architecture (no core/engine layer):

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

### service.py

Business logic for NAS file operations. All functions return Python objects (dict/list), not JSON strings. Key functions:
- `list_files(path, recursive)` → list of entry dicts
- `read_file(path, binary)` → text or base64 string
- `write_file(path, content, binary)` → status dict
- `delete_file(path)` / `move_file(src, dst)` / `copy_file(src, dst)` → status dict
- `file_info(path)` → metadata dict (size, timestamps, permissions)
- `search_files(pattern, path)` → list of matching relative paths
- `upload_files(directory, filenames, contents)` → list of status dicts (raw bytes, no base64)

Path security: `_safe_path()` resolves and validates all paths stay under `BASE_PATH`. `upload_files()` additionally sanitizes filenames via `os.path.basename()`.

### mcp_server.py

8 MCP tools (thin wrappers calling `service.*`, serializing with `json.dumps()`):
`list_files`, `read_file`, `write_file`, `delete_file`, `move_file`, `copy_file`, `file_info`, `search_files`

Supports `mount_mcp_sse(app)` for SSE integration and `--transport stdio|sse` for standalone use.

### api_server.py

FastAPI REST endpoints (mounted at `/api` by server.py). See [REST API Reference](#rest-api-reference) below.

### server.py

Unified entry point: mounts REST API at `/api`, MCP SSE at `/mcp`, healthcheck at `/healthcheck`.

## Build & Run

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

## Deployment

已改用 GitLab CI/CD 部署，push 到 GitLab 即觸發 build，deploy 手動觸發。詳見 [infrastructure.md](../infrastructure.md)。

| 項目 | 值 |
|------|---|
| Image | `192.168.1.152:5679/nas-files:latest` |
| NodePort | `30803` |
| GPU | — |

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

---

## REST API Reference

Base URL: `http://<host>:<port>/api`

Swagger UI: `/api/docs`

### POST `/api/upload/{directory}`

Multipart multi-file upload（核心功能，bypasses LLM）。

**Request:**
- Content-Type: `multipart/form-data`
- Body: `files` — 一或多個檔案

**路徑參數:**
- `directory` — 上傳目標目錄（相對於 NAS 根目錄）

**範例（curl）：**
```bash
curl -X POST http://host:30803/api/upload/dataset_name \
  -F "files=@photo1.jpg" -F "files=@photo2.jpg"
```

### GET `/api/files`

列出指定目錄下的檔案。

**Query 參數:**

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `path` | `str` | `.` | 目錄路徑（相對於 NAS 根目錄） |
| `recursive` | `bool` | `false` | 是否遞迴列出子目錄 |

**範例（curl）：**
```bash
curl "http://host:30803/api/files?path=.&recursive=false"
```

### GET `/api/files/info`

取得檔案或目錄的詳細資訊（大小、時間戳記、權限）。

**Query 參數:**

| 參數 | 型別 | 說明 |
|---|---|---|
| `path` | `str` | 檔案或目錄路徑 |

**範例（curl）：**
```bash
curl "http://host:30803/api/files/info?path=dataset/photo.jpg"
```

### GET `/api/files/search`

用 glob pattern 搜尋檔案。

**Query 參數:**

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `pattern` | `str` | （必填） | glob pattern（如 `*.jpg`） |
| `path` | `str` | `.` | 搜尋起始目錄 |

**範例（curl）：**
```bash
curl "http://host:30803/api/files/search?pattern=*.jpg&path=dataset"
```

### POST `/api/files/write`

寫入檔案內容。

**Request:**
- Content-Type: `application/json`
- Body:

| 欄位 | 型別 | 說明 |
|---|---|---|
| `path` | `str` | 檔案路徑 |
| `content` | `str` | 檔案內容 |

### DELETE `/api/files`

刪除檔案或空目錄。

**Query 參數:**

| 參數 | 型別 | 說明 |
|---|---|---|
| `path` | `str` | 要刪除的檔案或空目錄路徑 |

### POST `/api/files/move`

搬移檔案或目錄。

**Request:**
- Content-Type: `application/json`
- Body: `{"src": "...", "dst": "..."}`

### POST `/api/files/copy`

複製檔案或目錄。

**Request:**
- Content-Type: `application/json`
- Body: `{"src": "...", "dst": "..."}`

### GET `/healthcheck`

健康檢查端點（位於根路徑，非 `/api` 下）。

### 錯誤處理

- Global `ValueError` exception handler → HTTP 400
- 所有錯誤以 JSON 格式回傳
