CREATE EXTENSION IF NOT EXISTS vector;

-- projects
CREATE TABLE IF NOT EXISTS projects (
    project_id    SERIAL PRIMARY KEY,
    researcher_name TEXT NOT NULL,
    topic         TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- images (shared across projects and datasets)
CREATE TABLE IF NOT EXISTS images (
    image_id      SERIAL PRIMARY KEY,
    source_type   TEXT NOT NULL DEFAULT 'local',
    lat           DOUBLE PRECISION,
    lng           DOUBLE PRECISION,
    local_path    TEXT,
    remote_url    TEXT,
    checksum      TEXT,
    embedding     vector(512),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_images_embedding_hnsw ON images
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE UNIQUE INDEX IF NOT EXISTS idx_images_checksum ON images (checksum)
    WHERE checksum IS NOT NULL;

-- analysis_results (numeric results, links projects <-> images)
CREATE TABLE IF NOT EXISTS analysis_results (
    result_id     SERIAL PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    image_id      INTEGER NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    tool_name     TEXT NOT NULL,
    result_json   JSONB NOT NULL DEFAULT '{}',
    confidence    DOUBLE PRECISION,
    model_version TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_results_project_image ON analysis_results (project_id, image_id);
CREATE INDEX IF NOT EXISTS idx_results_tool ON analysis_results (tool_name);

-- datasets: registry of image collections
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id    SERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    description   TEXT,
    methodology   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- dataset_images: M:N link between datasets and images with curation metadata
CREATE TABLE IF NOT EXISTS dataset_images (
    dataset_id    INTEGER NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    image_id      INTEGER NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    metadata      JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (dataset_id, image_id)
);

CREATE INDEX IF NOT EXISTS idx_dataset_images_image ON dataset_images (image_id);
CREATE INDEX IF NOT EXISTS idx_dataset_images_metadata ON dataset_images USING gin (metadata);

-- image_descriptions: LLM-generated text descriptions with text embeddings
CREATE TABLE IF NOT EXISTS image_descriptions (
    description_id SERIAL PRIMARY KEY,
    project_id     INTEGER REFERENCES projects(project_id) ON DELETE CASCADE,
    image_id       INTEGER NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    tool_name      TEXT NOT NULL,
    content        TEXT NOT NULL,
    embedding      vector(1536),
    language       TEXT NOT NULL DEFAULT 'zh',
    model_version  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_descriptions_image ON image_descriptions (image_id);
CREATE INDEX IF NOT EXISTS idx_descriptions_project ON image_descriptions (project_id);
CREATE INDEX IF NOT EXISTS idx_descriptions_tool ON image_descriptions (tool_name);
CREATE INDEX IF NOT EXISTS idx_descriptions_embedding_hnsw ON image_descriptions
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- questionnaires: reusable survey templates for PRBot
CREATE TABLE IF NOT EXISTS questionnaires (
    questionnaire_id  SERIAL PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    description       TEXT,
    questions         JSONB NOT NULL,
    prompt_template   TEXT,
    scale_min         INTEGER NOT NULL DEFAULT 1,
    scale_max         INTEGER NOT NULL DEFAULT 5,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
