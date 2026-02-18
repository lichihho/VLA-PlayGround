"""MCP server for pg-vector — thin wrapper over service.py.

Run: python mcp_server.py              (stdio transport, default)
     python mcp_server.py --transport sse   (standalone SSE server on port 8001)

When integrated with server.py, use mount_mcp_sse(app) to mount at /mcp.
"""

import json

from mcp.server.fastmcp import FastMCP

import service

mcp = FastMCP(
    "pg-vector",
    instructions="PostgreSQL + pgvector database for managing research projects, images, analysis results, and vector similarity search",
)


@mcp.tool()
def create_project(researcher_name: str, topic: str) -> str:
    """Create a new research project.

    Args:
        researcher_name: Name of the researcher.
        topic: Research topic or description.

    Returns:
        JSON object with the created project details.
    """
    return json.dumps(service.create_project(researcher_name, topic), ensure_ascii=False)


@mcp.tool()
def get_project(project_id: int) -> str:
    """Get a project by ID.

    Args:
        project_id: The project ID.

    Returns:
        JSON object with project details.
    """
    return json.dumps(service.get_project(project_id), ensure_ascii=False)


@mcp.tool()
def list_projects() -> str:
    """List all research projects.

    Returns:
        JSON array of all projects.
    """
    return json.dumps(service.list_projects(), ensure_ascii=False)


@mcp.tool()
def delete_project(project_id: int) -> str:
    """Delete a project and all its analysis results (CASCADE).

    Args:
        project_id: The project ID to delete.

    Returns:
        Confirmation message.
    """
    return json.dumps(service.delete_project(project_id), ensure_ascii=False)


@mcp.tool()
def create_image(
    source_type: str = "local",
    lat: float | None = None,
    lng: float | None = None,
    local_path: str | None = None,
    remote_url: str | None = None,
    checksum: str | None = None,
) -> str:
    """Register a new image in the database.

    Args:
        source_type: Image source type (e.g. "local", "gsv", "url"). Defaults to "local".
        lat: Latitude coordinate.
        lng: Longitude coordinate.
        local_path: Path on the NAS file server.
        remote_url: Remote URL of the image.
        checksum: File checksum for deduplication.

    Returns:
        JSON object with the created image details.
    """
    return json.dumps(
        service.create_image(source_type, lat, lng, local_path, remote_url, checksum),
        ensure_ascii=False,
    )


@mcp.tool()
def get_image(image_id: int) -> str:
    """Get an image by ID.

    Args:
        image_id: The image ID.

    Returns:
        JSON object with image details.
    """
    return json.dumps(service.get_image(image_id), ensure_ascii=False)


@mcp.tool()
def list_images(limit: int = 50, offset: int = 0) -> str:
    """List images with pagination.

    Args:
        limit: Maximum number of images to return. Defaults to 50.
        offset: Number of images to skip. Defaults to 0.

    Returns:
        JSON array of images.
    """
    return json.dumps(service.list_images(limit, offset), ensure_ascii=False)


@mcp.tool()
def update_image_embedding(image_id: int, embedding: list[float]) -> str:
    """Update the embedding vector for an image.

    Args:
        image_id: The image ID.
        embedding: 512-dimensional float vector.

    Returns:
        JSON object with the updated image details.
    """
    return json.dumps(service.update_image_embedding(image_id, embedding), ensure_ascii=False)


@mcp.tool()
def create_analysis_result(
    project_id: int,
    image_id: int,
    tool_name: str,
    result_json: dict | None = None,
    confidence: float | None = None,
    model_version: str | None = None,
) -> str:
    """Store an analysis result linking a project and an image.

    Args:
        project_id: The project ID.
        image_id: The image ID.
        tool_name: Name of the analysis tool (e.g. "ladeco_predict").
        result_json: Analysis output as a JSON object.
        confidence: Confidence score (0.0 to 1.0).
        model_version: Version of the model used.

    Returns:
        JSON object with the created result details.
    """
    return json.dumps(
        service.create_analysis_result(project_id, image_id, tool_name, result_json, confidence, model_version),
        ensure_ascii=False,
    )


@mcp.tool()
def list_analysis_results(
    project_id: int | None = None,
    image_id: int | None = None,
    tool_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """List analysis results with optional filters.

    Args:
        project_id: Filter by project ID.
        image_id: Filter by image ID.
        tool_name: Filter by tool name.
        limit: Maximum number of results to return. Defaults to 50.
        offset: Number of results to skip. Defaults to 0.

    Returns:
        JSON array of matching analysis results.
    """
    return json.dumps(
        service.list_analysis_results(project_id, image_id, tool_name, limit, offset),
        ensure_ascii=False,
    )


@mcp.tool()
def search_similar_images(
    embedding: list[float],
    top_k: int = 10,
    threshold: float | None = None,
) -> str:
    """Search for images similar to a given embedding vector (cosine similarity).

    Args:
        embedding: 512-dimensional query vector.
        top_k: Number of results to return. Defaults to 10.
        threshold: Minimum similarity score (0.0 to 1.0). Optional.

    Returns:
        JSON array of similar images with similarity scores.
    """
    return json.dumps(
        service.search_similar_images(embedding, top_k, threshold),
        ensure_ascii=False,
    )


@mcp.tool()
def search_similar_by_image_id(
    image_id: int,
    top_k: int = 10,
    threshold: float | None = None,
) -> str:
    """Search for images similar to a given image (by image_id).

    Args:
        image_id: The source image ID to find similar images for.
        top_k: Number of results to return. Defaults to 10.
        threshold: Minimum similarity score (0.0 to 1.0). Optional.

    Returns:
        JSON array of similar images with similarity scores.
    """
    return json.dumps(
        service.search_similar_by_image_id(image_id, top_k, threshold),
        ensure_ascii=False,
    )


@mcp.tool()
def get_project_summary(project_id: int) -> str:
    """Get a summary of a project including image count, result count, and tools used.

    Args:
        project_id: The project ID.

    Returns:
        JSON object with project info and aggregated statistics.
    """
    return json.dumps(service.get_project_summary(project_id), ensure_ascii=False)


# ── Datasets ─────────────────────────────────────────────────────────


@mcp.tool()
def create_dataset(name: str, description: str | None = None, methodology: str | None = None) -> str:
    """Create a new dataset (image collection).

    Args:
        name: Unique dataset name (e.g. "preference-dataset").
        description: Brief description of the dataset.
        methodology: How the dataset was constructed.

    Returns:
        JSON object with the created dataset details.
    """
    return json.dumps(service.create_dataset(name, description, methodology), ensure_ascii=False)


@mcp.tool()
def get_dataset(dataset_id: int) -> str:
    """Get a dataset by ID.

    Args:
        dataset_id: The dataset ID.

    Returns:
        JSON object with dataset details.
    """
    return json.dumps(service.get_dataset(dataset_id), ensure_ascii=False)


@mcp.tool()
def list_datasets() -> str:
    """List all datasets.

    Returns:
        JSON array of all datasets.
    """
    return json.dumps(service.list_datasets(), ensure_ascii=False)


@mcp.tool()
def delete_dataset(dataset_id: int) -> str:
    """Delete a dataset and its image associations (CASCADE).

    Args:
        dataset_id: The dataset ID to delete.

    Returns:
        Confirmation message.
    """
    return json.dumps(service.delete_dataset(dataset_id), ensure_ascii=False)


@mcp.tool()
def get_dataset_summary(dataset_id: int) -> str:
    """Get a summary of a dataset including image count.

    Args:
        dataset_id: The dataset ID.

    Returns:
        JSON object with dataset info and statistics.
    """
    return json.dumps(service.get_dataset_summary(dataset_id), ensure_ascii=False)


@mcp.tool()
def add_image_to_dataset(dataset_id: int, image_id: int, metadata: dict | None = None) -> str:
    """Link an image to a dataset with optional curation metadata.

    Args:
        dataset_id: The dataset ID.
        image_id: The image ID to add.
        metadata: Curation metadata as JSON (e.g. dim, zscore, p365_class).

    Returns:
        JSON object with the created link details.
    """
    return json.dumps(service.add_image_to_dataset(dataset_id, image_id, metadata), ensure_ascii=False)


@mcp.tool()
def list_dataset_images(
    dataset_id: int,
    limit: int = 50,
    offset: int = 0,
    metadata_filter: dict | list[dict] | None = None,
    count_only: bool = False,
) -> str:
    """List images in a dataset with their curation metadata.

    Args:
        dataset_id: The dataset ID.
        limit: Maximum number of images to return. Defaults to 50.
        offset: Number of images to skip. Defaults to 0.
        metadata_filter: Filter by metadata fields using JSONB containment (@>).
            - Single dict: {"dim": "mountains, hills, desert, sky"}
            - List of dicts (OR): [{"dim": "water, ice, snow"}, {"dim": "forest, field, jungle"}]
        count_only: If True, return only the count instead of image list.

    Returns:
        JSON array of images with dataset_metadata, or {"count": N} if count_only.
    """
    return json.dumps(
        service.list_dataset_images(dataset_id, limit, offset, metadata_filter, count_only),
        ensure_ascii=False,
    )


# ── Questionnaires ────────────────────────────────────────────────────


@mcp.tool()
def create_questionnaire(
    name: str,
    questions: list[dict],
    description: str | None = None,
    prompt_template: str | None = None,
    scale_min: int = 1,
    scale_max: int = 5,
) -> str:
    """Create a new questionnaire (reusable survey template for PRBot).

    Args:
        name: Unique questionnaire name.
        questions: List of question objects (each with text, dimension, etc.).
        description: Brief description of the questionnaire.
        prompt_template: Prompt template for LLM-based evaluation.
        scale_min: Minimum scale value (default 1).
        scale_max: Maximum scale value (default 5).

    Returns:
        JSON object with the created questionnaire details.
    """
    return json.dumps(
        service.create_questionnaire(name, questions, description, prompt_template, scale_min, scale_max),
        ensure_ascii=False,
    )


@mcp.tool()
def get_questionnaire(questionnaire_id: int) -> str:
    """Get a questionnaire by ID.

    Args:
        questionnaire_id: The questionnaire ID.

    Returns:
        JSON object with questionnaire details.
    """
    return json.dumps(service.get_questionnaire(questionnaire_id), ensure_ascii=False)


@mcp.tool()
def list_questionnaires() -> str:
    """List all questionnaires.

    Returns:
        JSON array of all questionnaires.
    """
    return json.dumps(service.list_questionnaires(), ensure_ascii=False)


@mcp.tool()
def delete_questionnaire(questionnaire_id: int) -> str:
    """Delete a questionnaire.

    Args:
        questionnaire_id: The questionnaire ID to delete.

    Returns:
        Confirmation message.
    """
    return json.dumps(service.delete_questionnaire(questionnaire_id), ensure_ascii=False)


# ── Image Descriptions ───────────────────────────────────────────────


@mcp.tool()
def create_image_description(
    image_id: int,
    tool_name: str,
    content: str,
    project_id: int | None = None,
    language: str = "zh",
    model_version: str | None = None,
) -> str:
    """Store an LLM-generated text description for an image.

    Args:
        image_id: The image ID.
        tool_name: Name of the LLM tool (e.g. "claude_vision", "gpt4v").
        content: The text description content.
        project_id: Optional project ID to associate with.
        language: Language code (default "zh").
        model_version: Version of the model used.

    Returns:
        JSON object with the created description details.
    """
    return json.dumps(
        service.create_image_description(image_id, tool_name, content, project_id, None, language, model_version),
        ensure_ascii=False,
    )


@mcp.tool()
def list_image_descriptions(
    image_id: int | None = None,
    project_id: int | None = None,
    tool_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """List image descriptions with optional filters.

    Args:
        image_id: Filter by image ID.
        project_id: Filter by project ID.
        tool_name: Filter by tool name.
        limit: Maximum number of results to return. Defaults to 50.
        offset: Number of results to skip. Defaults to 0.

    Returns:
        JSON array of matching image descriptions.
    """
    return json.dumps(
        service.list_image_descriptions(image_id, project_id, tool_name, limit, offset),
        ensure_ascii=False,
    )


@mcp.tool()
def delete_image_description(description_id: int) -> str:
    """Delete an image description by its ID.

    Args:
        description_id: The description ID to delete.

    Returns:
        Confirmation message.
    """
    return json.dumps(service.delete_image_description(description_id), ensure_ascii=False)


def mount_mcp_sse(app):
    """Mount MCP SSE endpoints onto a FastAPI/Starlette app at /mcp.

    After mounting, the SSE endpoint is available at /mcp/sse
    and the message endpoint at /mcp/messages/.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )
    app.mount("/mcp", mcp.sse_app())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="pg-vector MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
