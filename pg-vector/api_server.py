"""REST API server for pg-vector service."""

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

import service

app = FastAPI(title="pg-vector API", version="1.0.0")

_EMBEDDING_DIM = 512


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


# ── Pydantic models ──────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    researcher_name: str
    topic: str


class ProjectUpdate(BaseModel):
    researcher_name: str | None = None
    topic: str | None = None


class ImageCreate(BaseModel):
    source_type: str = "local"
    lat: float | None = None
    lng: float | None = None
    local_path: str | None = None
    remote_url: str | None = None
    checksum: str | None = None
    embedding: list[float] | None = None

    @field_validator("embedding")
    @classmethod
    def check_embedding_dim(cls, v):
        if v is not None and len(v) != _EMBEDDING_DIM:
            raise ValueError(f"Embedding must be {_EMBEDDING_DIM}-dimensional, got {len(v)}")
        return v


class EmbeddingUpdate(BaseModel):
    embedding: list[float]

    @field_validator("embedding")
    @classmethod
    def check_embedding_dim(cls, v):
        if len(v) != _EMBEDDING_DIM:
            raise ValueError(f"Embedding must be {_EMBEDDING_DIM}-dimensional, got {len(v)}")
        return v


class ResultCreate(BaseModel):
    project_id: int
    image_id: int
    tool_name: str
    result_json: dict | None = None
    confidence: float | None = None
    model_version: str | None = None


class DatasetCreate(BaseModel):
    name: str
    description: str | None = None
    methodology: str | None = None


class DatasetImageAdd(BaseModel):
    dataset_id: int
    image_id: int
    metadata: dict | None = None


class DescriptionCreate(BaseModel):
    image_id: int
    tool_name: str
    content: str
    project_id: int | None = None
    embedding: list[float] | None = None
    language: str = "zh"
    model_version: str | None = None

    @field_validator("embedding")
    @classmethod
    def check_embedding_dim(cls, v):
        if v is not None and len(v) != 1536:
            raise ValueError(f"Text embedding must be 1536-dimensional, got {len(v)}")
        return v


class SimilarDescriptionSearch(BaseModel):
    embedding: list[float]
    top_k: int = 10
    threshold: float | None = None

    @field_validator("embedding")
    @classmethod
    def check_embedding_dim(cls, v):
        if len(v) != 1536:
            raise ValueError(f"Text embedding must be 1536-dimensional, got {len(v)}")
        return v


class SimilarSearch(BaseModel):
    embedding: list[float]
    top_k: int = 10
    threshold: float | None = None

    @field_validator("embedding")
    @classmethod
    def check_embedding_dim(cls, v):
        if len(v) != _EMBEDDING_DIM:
            raise ValueError(f"Embedding must be {_EMBEDDING_DIM}-dimensional, got {len(v)}")
        return v


# ── Projects ─────────────────────────────────────────────────────────


@app.post("/projects", status_code=201)
def create_project(body: ProjectCreate):
    return JSONResponse(status_code=201, content=service.create_project(body.researcher_name, body.topic))


@app.get("/projects")
def list_projects():
    return JSONResponse(content=service.list_projects())


@app.get("/projects/{project_id}")
def get_project(project_id: int):
    return JSONResponse(content=service.get_project(project_id))


@app.put("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate):
    return JSONResponse(content=service.update_project(project_id, body.researcher_name, body.topic))


@app.delete("/projects/{project_id}")
def delete_project(project_id: int):
    return JSONResponse(content=service.delete_project(project_id))


@app.get("/projects/{project_id}/summary")
def get_project_summary(project_id: int):
    return JSONResponse(content=service.get_project_summary(project_id))


@app.get("/projects/{project_id}/images")
def get_project_images(project_id: int):
    return JSONResponse(content=service.get_project_images(project_id))


# ── Images ───────────────────────────────────────────────────────────


@app.post("/images", status_code=201)
def create_image(body: ImageCreate):
    return JSONResponse(
        status_code=201,
        content=service.create_image(
            body.source_type, body.lat, body.lng,
            body.local_path, body.remote_url, body.checksum, body.embedding,
        ),
    )


@app.get("/images")
def list_images(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return JSONResponse(content=service.list_images(limit, offset))


@app.get("/images/{image_id}")
def get_image(image_id: int):
    return JSONResponse(content=service.get_image(image_id))


@app.put("/images/{image_id}/embedding")
def update_image_embedding(image_id: int, body: EmbeddingUpdate):
    return JSONResponse(content=service.update_image_embedding(image_id, body.embedding))


@app.delete("/images/{image_id}")
def delete_image(image_id: int):
    return JSONResponse(content=service.delete_image(image_id))


# ── Analysis Results ─────────────────────────────────────────────────


@app.post("/results", status_code=201)
def create_analysis_result(body: ResultCreate):
    return JSONResponse(
        status_code=201,
        content=service.create_analysis_result(
            body.project_id, body.image_id, body.tool_name,
            body.result_json, body.confidence, body.model_version,
        ),
    )


@app.get("/results")
def list_analysis_results(
    project_id: int | None = Query(None),
    image_id: int | None = Query(None),
    tool_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return JSONResponse(content=service.list_analysis_results(project_id, image_id, tool_name, limit, offset))


@app.get("/results/{result_id}")
def get_analysis_result(result_id: int):
    return JSONResponse(content=service.get_analysis_result(result_id))


@app.delete("/results/{result_id}")
def delete_analysis_result(result_id: int):
    return JSONResponse(content=service.delete_analysis_result(result_id))


# ── Vector Search ────────────────────────────────────────────────────


@app.post("/search/similar")
def search_similar(body: SimilarSearch):
    return JSONResponse(content=service.search_similar_images(body.embedding, body.top_k, body.threshold))


@app.get("/search/similar/{image_id}")
def search_similar_by_image(
    image_id: int,
    top_k: int = Query(10, ge=1, le=100),
    threshold: float | None = Query(None),
):
    return JSONResponse(content=service.search_similar_by_image_id(image_id, top_k, threshold))


# ── Datasets ────────────────────────────────────────────────────────


@app.post("/datasets", status_code=201)
def create_dataset(body: DatasetCreate):
    return JSONResponse(status_code=201, content=service.create_dataset(body.name, body.description, body.methodology))


@app.get("/datasets")
def list_datasets():
    return JSONResponse(content=service.list_datasets())


@app.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: int):
    return JSONResponse(content=service.get_dataset(dataset_id))


@app.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: int):
    return JSONResponse(content=service.delete_dataset(dataset_id))


@app.get("/datasets/{dataset_id}/summary")
def get_dataset_summary(dataset_id: int):
    return JSONResponse(content=service.get_dataset_summary(dataset_id))


@app.post("/datasets/images", status_code=201)
def add_image_to_dataset(body: DatasetImageAdd):
    return JSONResponse(
        status_code=201,
        content=service.add_image_to_dataset(body.dataset_id, body.image_id, body.metadata),
    )


@app.get("/datasets/{dataset_id}/images")
def list_dataset_images(
    dataset_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    dim: str | None = Query(None, description="Filter by dim metadata field"),
    count_only: bool = Query(False, description="Return only count"),
):
    metadata_filter = {}
    if dim is not None:
        metadata_filter["dim"] = dim
    return JSONResponse(
        content=service.list_dataset_images(
            dataset_id, limit, offset,
            metadata_filter if metadata_filter else None,
            count_only,
        ),
    )


# ── Image Descriptions ──────────────────────────────────────────────


@app.post("/descriptions", status_code=201)
def create_description(body: DescriptionCreate):
    return JSONResponse(
        status_code=201,
        content=service.create_image_description(
            body.image_id, body.tool_name, body.content,
            body.project_id, body.embedding, body.language, body.model_version,
        ),
    )


@app.get("/descriptions")
def list_descriptions(
    image_id: int | None = Query(None),
    project_id: int | None = Query(None),
    tool_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return JSONResponse(content=service.list_image_descriptions(image_id, project_id, tool_name, limit, offset))


@app.post("/search/similar-descriptions")
def search_similar_descriptions(body: SimilarDescriptionSearch):
    return JSONResponse(content=service.search_similar_descriptions(body.embedding, body.top_k, body.threshold))
