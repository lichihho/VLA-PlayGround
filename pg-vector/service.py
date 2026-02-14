"""Business logic for pg-vector service.

All functions return Python objects (dict/list) and raise ValueError on errors.
"""

import json

from psycopg.rows import dict_row

import db

_EMBEDDING_DIM = 512
_TEXT_EMBEDDING_DIM = 1536


def _validate_embedding(embedding: list[float], dim: int = _EMBEDDING_DIM) -> str:
    """Validate dimension and convert to pgvector-compatible string."""
    if len(embedding) != dim:
        raise ValueError(f"Embedding must be {dim}-dimensional, got {len(embedding)}")
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _serialize_row(row: dict) -> dict:
    """Convert a DB row to a JSON-safe dict."""
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, str) and k == "embedding":
            out[k] = json.loads(v)
        else:
            out[k] = v
    return out


# ── Projects ──────────────────────────────────────────────────────────


def create_project(researcher_name: str, topic: str) -> dict:
    """Create a new project."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO projects (researcher_name, topic) "
                "VALUES (%s, %s) RETURNING *",
                (researcher_name, topic),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(row)


def get_project(project_id: int) -> dict:
    """Get a project by ID."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM projects WHERE project_id = %s", (project_id,))
            row = cur.fetchone()
    if row is None:
        raise ValueError(f"Project not found: {project_id}")
    return _serialize_row(row)


def list_projects() -> list[dict]:
    """List all projects."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM projects ORDER BY project_id")
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def update_project(project_id: int, researcher_name: str | None = None, topic: str | None = None) -> dict:
    """Update a project's fields."""
    updates = []
    params = []
    if researcher_name is not None:
        updates.append("researcher_name = %s")
        params.append(researcher_name)
    if topic is not None:
        updates.append("topic = %s")
        params.append(topic)
    if not updates:
        raise ValueError("No fields to update")

    params.append(project_id)
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"UPDATE projects SET {', '.join(updates)} WHERE project_id = %s RETURNING *",
                params,
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise ValueError(f"Project not found: {project_id}")
    return _serialize_row(row)


def delete_project(project_id: int) -> dict:
    """Delete a project (cascades to analysis_results)."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM projects WHERE project_id = %s RETURNING project_id", (project_id,))
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise ValueError(f"Project not found: {project_id}")
    return {"status": "ok", "deleted_project_id": row[0]}


# ── Images ────────────────────────────────────────────────────────────


def create_image(
    source_type: str = "local",
    lat: float | None = None,
    lng: float | None = None,
    local_path: str | None = None,
    remote_url: str | None = None,
    checksum: str | None = None,
    embedding: list[float] | None = None,
) -> dict:
    """Register a new image."""
    emb_str = _validate_embedding(embedding) if embedding is not None else None
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO images (source_type, lat, lng, local_path, remote_url, checksum, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (source_type, lat, lng, local_path, remote_url, checksum, emb_str),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(row)


def get_image(image_id: int) -> dict:
    """Get an image by ID."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM images WHERE image_id = %s", (image_id,))
            row = cur.fetchone()
    if row is None:
        raise ValueError(f"Image not found: {image_id}")
    return _serialize_row(row)


def list_images(limit: int = 50, offset: int = 0) -> list[dict]:
    """List images with pagination."""
    if not (1 <= limit <= 500):
        raise ValueError("limit must be between 1 and 500")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM images ORDER BY image_id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def update_image_embedding(image_id: int, embedding: list[float]) -> dict:
    """Update the embedding vector for an image."""
    emb_str = _validate_embedding(embedding)
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "UPDATE images SET embedding = %s WHERE image_id = %s RETURNING *",
                (emb_str, image_id),
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise ValueError(f"Image not found: {image_id}")
    return _serialize_row(row)


def delete_image(image_id: int) -> dict:
    """Delete an image (cascades to analysis_results)."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM images WHERE image_id = %s RETURNING image_id", (image_id,))
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise ValueError(f"Image not found: {image_id}")
    return {"status": "ok", "deleted_image_id": row[0]}


# ── Analysis Results ──────────────────────────────────────────────────


def create_analysis_result(
    project_id: int,
    image_id: int,
    tool_name: str,
    result_json: dict | None = None,
    confidence: float | None = None,
    model_version: str | None = None,
) -> dict:
    """Store an analysis result."""
    rj = json.dumps(result_json or {})
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO analysis_results "
                "(project_id, image_id, tool_name, result_json, confidence, model_version) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
                (project_id, image_id, tool_name, rj, confidence, model_version),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(row)


def get_analysis_result(result_id: int) -> dict:
    """Get an analysis result by ID."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM analysis_results WHERE result_id = %s", (result_id,))
            row = cur.fetchone()
    if row is None:
        raise ValueError(f"Result not found: {result_id}")
    return _serialize_row(row)


def list_analysis_results(
    project_id: int | None = None,
    image_id: int | None = None,
    tool_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List analysis results with optional filters."""
    if not (1 <= limit <= 500):
        raise ValueError("limit must be between 1 and 500")
    if offset < 0:
        raise ValueError("offset must be non-negative")

    conditions = []
    params: list = []
    if project_id is not None:
        conditions.append("project_id = %s")
        params.append(project_id)
    if image_id is not None:
        conditions.append("image_id = %s")
        params.append(image_id)
    if tool_name is not None:
        conditions.append("tool_name = %s")
        params.append(tool_name)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT * FROM analysis_results{where} ORDER BY result_id LIMIT %s OFFSET %s",
                params,
            )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def delete_analysis_result(result_id: int) -> dict:
    """Delete an analysis result."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM analysis_results WHERE result_id = %s RETURNING result_id",
                (result_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise ValueError(f"Result not found: {result_id}")
    return {"status": "ok", "deleted_result_id": row[0]}


# ── Vector Search ─────────────────────────────────────────────────────


def search_similar_images(
    embedding: list[float],
    top_k: int = 10,
    threshold: float | None = None,
) -> list[dict]:
    """Search for similar images by embedding vector (cosine distance)."""
    if not (1 <= top_k <= 100):
        raise ValueError("top_k must be between 1 and 100")
    if threshold is not None and not (0.0 <= threshold <= 1.0):
        raise ValueError("threshold must be between 0.0 and 1.0")

    emb_str = _validate_embedding(embedding)
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if threshold is not None:
                cur.execute(
                    "WITH query AS (SELECT %s::vector AS emb) "
                    "SELECT i.*, 1 - (i.embedding <=> q.emb) AS similarity "
                    "FROM images i, query q "
                    "WHERE i.embedding IS NOT NULL "
                    "AND 1 - (i.embedding <=> q.emb) >= %s "
                    "ORDER BY i.embedding <=> q.emb LIMIT %s",
                    (emb_str, threshold, top_k),
                )
            else:
                cur.execute(
                    "WITH query AS (SELECT %s::vector AS emb) "
                    "SELECT i.*, 1 - (i.embedding <=> q.emb) AS similarity "
                    "FROM images i, query q "
                    "WHERE i.embedding IS NOT NULL "
                    "ORDER BY i.embedding <=> q.emb LIMIT %s",
                    (emb_str, top_k),
                )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def search_similar_by_image_id(
    image_id: int,
    top_k: int = 10,
    threshold: float | None = None,
) -> list[dict]:
    """Search for images similar to a given image (by image_id)."""
    if not (1 <= top_k <= 100):
        raise ValueError("top_k must be between 1 and 100")
    if threshold is not None and not (0.0 <= threshold <= 1.0):
        raise ValueError("threshold must be between 0.0 and 1.0")

    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT embedding FROM images WHERE image_id = %s", (image_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Image not found: {image_id}")
            if row["embedding"] is None:
                raise ValueError(f"Image {image_id} has no embedding")

            if threshold is not None:
                cur.execute(
                    "SELECT i.*, 1 - (i.embedding <=> "
                    "  (SELECT embedding FROM images WHERE image_id = %s)) AS similarity "
                    "FROM images i "
                    "WHERE i.embedding IS NOT NULL AND i.image_id != %s "
                    "AND 1 - (i.embedding <=> "
                    "  (SELECT embedding FROM images WHERE image_id = %s)) >= %s "
                    "ORDER BY i.embedding <=> "
                    "  (SELECT embedding FROM images WHERE image_id = %s) LIMIT %s",
                    (image_id, image_id, image_id, threshold, image_id, top_k),
                )
            else:
                cur.execute(
                    "SELECT i.*, 1 - (i.embedding <=> "
                    "  (SELECT embedding FROM images WHERE image_id = %s)) AS similarity "
                    "FROM images i "
                    "WHERE i.embedding IS NOT NULL AND i.image_id != %s "
                    "ORDER BY i.embedding <=> "
                    "  (SELECT embedding FROM images WHERE image_id = %s) LIMIT %s",
                    (image_id, image_id, image_id, top_k),
                )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


# ── Project Aggregation ───────────────────────────────────────────────


def get_project_images(project_id: int) -> list[dict]:
    """Get all images associated with a project (via analysis_results)."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT DISTINCT i.* FROM images i "
                "JOIN analysis_results ar ON i.image_id = ar.image_id "
                "WHERE ar.project_id = %s ORDER BY i.image_id",
                (project_id,),
            )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def get_project_summary(project_id: int) -> dict:
    """Get a summary of a project including counts and tool usage."""
    project = get_project(project_id)
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT image_id) AS image_count, "
                "COUNT(*) AS result_count "
                "FROM analysis_results WHERE project_id = %s",
                (project_id,),
            )
            counts = cur.fetchone()
            cur.execute(
                "SELECT tool_name, COUNT(*) AS count "
                "FROM analysis_results WHERE project_id = %s "
                "GROUP BY tool_name ORDER BY count DESC",
                (project_id,),
            )
            tools = cur.fetchall()
    return {
        **project,
        "image_count": counts["image_count"],
        "result_count": counts["result_count"],
        "tools_used": [dict(t) for t in tools],
    }


# ── Datasets ─────────────────────────────────────────────────────────


def create_dataset(name: str, description: str | None = None, methodology: str | None = None) -> dict:
    """Create a new dataset."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO datasets (name, description, methodology) "
                "VALUES (%s, %s, %s) RETURNING *",
                (name, description, methodology),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(row)


def get_dataset(dataset_id: int) -> dict:
    """Get a dataset by ID."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM datasets WHERE dataset_id = %s", (dataset_id,))
            row = cur.fetchone()
    if row is None:
        raise ValueError(f"Dataset not found: {dataset_id}")
    return _serialize_row(row)


def list_datasets() -> list[dict]:
    """List all datasets."""
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM datasets ORDER BY dataset_id")
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def delete_dataset(dataset_id: int) -> dict:
    """Delete a dataset (cascades to dataset_images)."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM datasets WHERE dataset_id = %s RETURNING dataset_id", (dataset_id,))
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise ValueError(f"Dataset not found: {dataset_id}")
    return {"status": "ok", "deleted_dataset_id": row[0]}


def get_dataset_summary(dataset_id: int) -> dict:
    """Get a summary of a dataset including image count and metadata stats."""
    dataset = get_dataset(dataset_id)
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS image_count FROM dataset_images WHERE dataset_id = %s",
                (dataset_id,),
            )
            counts = cur.fetchone()
    return {**dataset, "image_count": counts["image_count"]}


# ── Dataset Images ───────────────────────────────────────────────────


def add_image_to_dataset(dataset_id: int, image_id: int, metadata: dict | None = None) -> dict:
    """Link an image to a dataset with curation metadata."""
    rj = json.dumps(metadata or {})
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO dataset_images (dataset_id, image_id, metadata) "
                "VALUES (%s, %s, %s) RETURNING *",
                (dataset_id, image_id, rj),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(row)


def list_dataset_images(
    dataset_id: int,
    limit: int = 50,
    offset: int = 0,
    metadata_filter: dict | list[dict] | None = None,
    count_only: bool = False,
) -> list[dict] | dict:
    """List images in a dataset with their curation metadata.

    Args:
        metadata_filter: JSONB containment filter using PostgreSQL @> operator.
            - dict: single filter, e.g. {"dim": "mountains"} → AND
            - list[dict]: multiple filters combined with OR,
              e.g. [{"dim": "forest"}, {"dim": "water"}] → matches either
        count_only: If True, return {"count": N} instead of image list.
    """
    if not (1 <= limit <= 500):
        raise ValueError("limit must be between 1 and 500")

    conditions = ["di.dataset_id = %s"]
    params: list = [dataset_id]

    if metadata_filter:
        if isinstance(metadata_filter, list):
            or_parts = []
            for f in metadata_filter:
                or_parts.append("di.metadata @> %s::jsonb")
                params.append(json.dumps(f))
            conditions.append("(" + " OR ".join(or_parts) + ")")
        else:
            conditions.append("di.metadata @> %s::jsonb")
            params.append(json.dumps(metadata_filter))

    where = " WHERE " + " AND ".join(conditions)

    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if count_only:
                cur.execute(
                    "SELECT COUNT(*) AS count "
                    "FROM dataset_images di " + where,
                    params,
                )
                return dict(cur.fetchone())

            params.extend([limit, offset])
            cur.execute(
                "SELECT i.*, di.metadata AS dataset_metadata "
                "FROM dataset_images di "
                "JOIN images i ON i.image_id = di.image_id "
                + where +
                " ORDER BY i.image_id LIMIT %s OFFSET %s",
                params,
            )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def remove_image_from_dataset(dataset_id: int, image_id: int) -> dict:
    """Remove an image from a dataset."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM dataset_images WHERE dataset_id = %s AND image_id = %s "
                "RETURNING dataset_id, image_id",
                (dataset_id, image_id),
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise ValueError(f"Image {image_id} not in dataset {dataset_id}")
    return {"status": "ok", "dataset_id": row[0], "image_id": row[1]}


# ── Image Descriptions ───────────────────────────────────────────────


def create_image_description(
    image_id: int,
    tool_name: str,
    content: str,
    project_id: int | None = None,
    embedding: list[float] | None = None,
    language: str = "zh",
    model_version: str | None = None,
) -> dict:
    """Store an LLM-generated text description for an image."""
    emb_str = _validate_embedding(embedding, _TEXT_EMBEDDING_DIM) if embedding is not None else None
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO image_descriptions "
                "(project_id, image_id, tool_name, content, embedding, language, model_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (project_id, image_id, tool_name, content, emb_str, language, model_version),
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize_row(row)


def list_image_descriptions(
    image_id: int | None = None,
    project_id: int | None = None,
    tool_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List image descriptions with optional filters."""
    if not (1 <= limit <= 500):
        raise ValueError("limit must be between 1 and 500")
    conditions = []
    params: list = []
    if image_id is not None:
        conditions.append("image_id = %s")
        params.append(image_id)
    if project_id is not None:
        conditions.append("project_id = %s")
        params.append(project_id)
    if tool_name is not None:
        conditions.append("tool_name = %s")
        params.append(tool_name)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT * FROM image_descriptions{where} ORDER BY description_id LIMIT %s OFFSET %s",
                params,
            )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def search_similar_descriptions(
    embedding: list[float],
    top_k: int = 10,
    threshold: float | None = None,
) -> list[dict]:
    """Search for similar text descriptions by embedding vector (cosine distance)."""
    if not (1 <= top_k <= 100):
        raise ValueError("top_k must be between 1 and 100")
    emb_str = _validate_embedding(embedding, _TEXT_EMBEDDING_DIM)
    with db.get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if threshold is not None:
                cur.execute(
                    "WITH query AS (SELECT %s::vector AS emb) "
                    "SELECT d.*, i.local_path, 1 - (d.embedding <=> q.emb) AS similarity "
                    "FROM image_descriptions d "
                    "JOIN images i ON i.image_id = d.image_id, query q "
                    "WHERE d.embedding IS NOT NULL "
                    "AND 1 - (d.embedding <=> q.emb) >= %s "
                    "ORDER BY d.embedding <=> q.emb LIMIT %s",
                    (emb_str, threshold, top_k),
                )
            else:
                cur.execute(
                    "WITH query AS (SELECT %s::vector AS emb) "
                    "SELECT d.*, i.local_path, 1 - (d.embedding <=> q.emb) AS similarity "
                    "FROM image_descriptions d "
                    "JOIN images i ON i.image_id = d.image_id, query q "
                    "WHERE d.embedding IS NOT NULL "
                    "ORDER BY d.embedding <=> q.emb LIMIT %s",
                    (emb_str, top_k),
                )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]
