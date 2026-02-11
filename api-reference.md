# REST API 參考文件

LaDeco REST API 掛載於 `/api` 路徑下，由 `api_server.py` 提供。

Base URL: `http://<host>:<port>/api`

## `level` 參數說明

多數端點支援 `level` 參數，用於指定分析的標籤階層層級：

| level | 說明 | 類別數 |
|---|---|---|
| 1 | 自然 / 人造 | 2 |
| 2 | 生物、地形、天空、植被、水體、建築、街道 | 7 |
| 3 | 草本、木本、水平水體、垂直水體 等 | 16 |
| 4 | 樹、草、道路、建築物、汽車 等 | ~50 |

- **面積資料端點**（`/predict`）：`level` 為選填，省略時回傳 L1-L4 全部；指定時只回傳該階層的面積比例。
- **視覺化端點**（`/visualize`、`/predict/batch`）：`level` 決定分割圖與圓餅圖使用的階層，預設為 2。

## Endpoints

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

---

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

---

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

---

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

---

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

---

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

---

### GET `/healthcheck`

健康檢查端點（位於根路徑，非 `/api` 下）。

**Response:**
```json
{"msg": "ladeco is alive"}
```

## 錯誤回應

所有錯誤以 JSON 格式回傳：

```json
{"error": "File not found"}
```

常見狀態碼：
- `404` — 檔案不存在或路徑無效
- `422` — 請求參數驗證失敗（FastAPI 自動處理）
- `500` — 內部錯誤（模型推論失敗等）
