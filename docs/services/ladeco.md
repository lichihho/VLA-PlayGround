# LaDeco — 景觀影像語意分割服務

## Overview

LaDeco (Landscape Decoration) is a landscape image semantic segmentation tool based on the OneFormer model (ADE20K dataset). It maps ADE20K's 150 classes into a custom 4-level hierarchical label system (L1–L4) and computes area ratios plus a Natural Feature Index (LC_NFI).

Reference: Li-Chih Ho (2023), *LaDeco: A Tool to Analyze Visual Landscape Elements*, Ecological Informatics, vol. 78.

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

### engine.py

The `Ladeco` class loads `shi-labs/oneformer_ade20k_swin_large` and exposes `predict()`. Returns a `LadecoOutput` object with:
- `visualize(level)` → colored segmentation maps as matplotlib Figures
- `area()` → per-image dict of all label area ratios + `others` + `LC_NFI`
- `color_map(level)` / `color_legend(level)` → viridis-based coloring (available both on `Ladeco` and `LadecoOutput`)

Module-level `_build_color_map()` and `_build_color_legend()` are shared by both classes.

The label hierarchy is built bottom-up in `_get_ladeco_labels()`: L4 labels map to ADE20K indices, then L3/L2/L1 aggregate by tuple concatenation.

### service.py

Business logic layer (model singleton, inference pipelines, CSV export, dataset listing, chart plotting). Key functions:
- `predict_batch(dataset, callback)` → `BatchResult` dataclass
- `predict_images(paths, callback)` → list of area dicts
- `visualize_image(path, level)` → (Figure, area_dict)
- `get_area(path, level)` → area dict (no visualization)
- `list_datasets()` / `preview_dataset(name)` → NAS dataset browsing
- `get_color_legend(level)` / `get_label_hierarchy()` → metadata
- `fig2img(fig)` / `plot_pie(data, colors)` → chart utilities

### api_server.py

REST API endpoints (mounted at `/api` by server.py). See [REST API Reference](#rest-api-reference) below.

### mcp_server.py

9 MCP tools for Claude Code (stdio transport):
`predict`, `predict_batch`, `predict_images`, `visualize`, `get_area`, `list_datasets`, `preview_dataset`, `get_color_legend`, `get_label_hierarchy`

MCP tool behavior: `predict`, `predict_images`, `get_area` default to `level=2` (L2). Tool docstrings instruct Claude to ask the user which hierarchy level (L1–L4) they need before calling; if the user does not specify, use the default L2.

### server.py

Unified entry point: mounts REST API at `/api`, MCP SSE at `/mcp`, healthcheck at `/healthcheck`.

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

部署在 K8s cluster (MicroK8s)，詳見 [infrastructure.md](../infrastructure.md)。

| 項目 | 值 |
|------|---|
| Image | `localhost:32000/ladeco-internal:latest` |
| NodePort | `30800` |
| GPU | 1× NVIDIA |

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

---

## REST API Reference

Base URL: `http://<host>:<port>/api`

Swagger UI: `/api/docs`

### `level` 參數說明

多數端點支援 `level` 參數，用於指定分析的標籤階層層級：

| level | 說明 | 類別數 |
|---|---|---|
| 1 | 自然 / 人造 | 2 |
| 2 | 生物、地形、天空、植被、水體、建築、街道 | 7 |
| 3 | 草本、木本、水平水體、垂直水體 等 | 16 |
| 4 | 樹、草、道路、建築物、汽車 等 | ~50 |

- **面積資料端點**（`/predict`）：`level` 為選填，省略時回傳 L1-L4 全部；指定時只回傳該階層的面積比例。
- **視覺化端點**（`/visualize`、`/predict/batch`）：`level` 決定分割圖與圓餅圖使用的階層，預設為 2。

### POST `/api/predict`

上傳單張影像，回傳面積比例。

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` — 影像檔案（JPG、PNG、BMP、TIFF、WebP）

**Query 參數:**

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `level` | `int`（1-4） | 無（回傳全部） | 篩選特定階層。省略則回傳 L1-L4 所有面積比例 |

**Response（省略 level，回傳全部）：**
```json
{
  "fid": "example.jpg",
  "l1_nature": 0.673,
  "l1_man_made": 0.241,
  "l2_bio": 0.012,
  "l2_landform": 0.15,
  "l2_sky": 0.32,
  "l2_vegetation": 0.191,
  "l2_water": 0.0,
  "l2_archi": 0.12,
  "l2_street": 0.121,
  "l3_hori_land": 0.10,
  "...": "...",
  "others": 0.086,
  "LC_NFI": 0.7361
}
```

**Response（level=3，只回傳 L3）：**
```json
{
  "fid": "example.jpg",
  "l3_hori_land": 0.10,
  "l3_vert_land": 0.05,
  "l3_flower": 0.0,
  "l3_herb_plant": 0.12,
  "l3_woody_plant": 0.071,
  "l3_hori_water": 0.0,
  "l3_vert_water": 0.0,
  "l3_animal": 0.0,
  "l3_human": 0.012,
  "l3_sky": 0.32,
  "l3_archi_parts": 0.04,
  "l3_architecture": 0.08,
  "l3_furniture": 0.021,
  "l3_roadway": 0.08,
  "l3_sign": 0.01,
  "l3_vehicle": 0.01,
  "others": 0.086,
  "LC_NFI": 0.7361
}
```

**範例（curl）：**
```bash
# 回傳全部階層
curl -X POST -F "file=@examples/field.jpg" http://localhost:8000/api/predict

# 只回傳 L3
curl -X POST -F "file=@examples/field.jpg" "http://localhost:8000/api/predict?level=3"
```

### POST `/api/predict/batch`

批次推論 NAS 資料集中的所有影像。

**Request:**
- Content-Type: `application/json`
- Body:

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `dataset` | `str` | （必填） | NAS 資料集目錄名稱 |
| `level` | `int`（1-4） | `2` | 分割圖與圓餅圖的標籤階層層級 |

```json
{
  "dataset": "my_dataset",
  "level": 3
}
```

**Response:**
```json
{
  "csv_path": "LaDeco-my_dataset-2024Jan01-120000-xxxxx.csv",
  "count": 42,
  "areas": [
    {
      "fid": "my_dataset/img001.jpg",
      "l1_nature": 0.55,
      "l1_man_made": 0.35,
      "...": "...",
      "others": 0.10,
      "LC_NFI": 0.6111
    }
  ]
}
```

> 注意：`areas` 中的面積資料始終包含 L1-L4 全部階層。`level` 參數僅影響分割圖與圓餅圖的視覺化。

**範例（curl）：**
```bash
# 預設 L2 視覺化
curl -X POST -H "Content-Type: application/json" \
  -d '{"dataset": "my_dataset"}' \
  http://localhost:8000/api/predict/batch

# 指定 L4 視覺化
curl -X POST -H "Content-Type: application/json" \
  -d '{"dataset": "my_dataset", "level": 4}' \
  http://localhost:8000/api/predict/batch
```

### POST `/api/visualize`

上傳單張影像，回傳語意分割圖（base64 PNG）與面積比例。

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` — 影像檔案

**Query 參數:**

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `level` | `int`（1-4） | `2` | 分割圖的標籤階層層級 |

**Response:**
```json
{
  "segmentation_png": "<base64 encoded PNG>",
  "area": {
    "fid": "example.jpg",
    "l1_nature": 0.673,
    "...": "...",
    "LC_NFI": 0.7361
  }
}
```

**範例（curl）：**
```bash
# L2 分割圖（預設）
curl -X POST -F "file=@examples/field.jpg" \
  "http://localhost:8000/api/visualize"

# L4 分割圖
curl -X POST -F "file=@examples/field.jpg" \
  "http://localhost:8000/api/visualize?level=4"
```

### GET `/api/datasets`

列出 NAS 上所有可用的資料集。

**Response:**
```json
[
  {"name": "campus_photos", "path": "campus_photos"},
  {"name": "park_survey", "path": "park_survey"}
]
```

**範例（curl）：**
```bash
curl http://localhost:8000/api/datasets
```

### GET `/api/datasets/{name}/preview`

預覽資料集中的影像檔案清單。

**Query 參數:**

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `max_items` | `int`（1-100） | `10` | 最多回傳幾筆 |

**Response:**
```json
[
  {"path": "/mnt/ai_data/campus_photos/img001.jpg", "filename": "img001.jpg"},
  {"path": "/mnt/ai_data/campus_photos/img002.jpg", "filename": "img002.jpg"}
]
```

**範例（curl）：**
```bash
curl "http://localhost:8000/api/datasets/campus_photos/preview?max_items=5"
```

### GET `/api/download/{filename}`

下載推論結果的 CSV 檔案。

**路徑參數:**
- `filename` — CSV 檔案名稱（必須以 `LaDeco-` 開頭）

**Response:**
- Content-Type: `text/csv`
- 檔案內容

**範例（curl）：**
```bash
curl -O "http://localhost:8000/api/download/LaDeco-field.jpg-2024Jan01-120000-xxxxx.csv"
```

### GET `/healthcheck`

健康檢查端點（位於根路徑，非 `/api` 下）。

**Response:**
```json
{"msg": "ladeco is alive"}
```

### 錯誤回應

所有錯誤以 JSON 格式回傳：

```json
{"error": "File not found"}
```

常見狀態碼：
- `404` — 檔案不存在或路徑無效
- `422` — 請求參數驗證失敗（FastAPI 自動處理）
- `500` — 內部錯誤（模型推論失敗等）
