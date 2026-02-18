-- Migration: Add questionnaires table
-- Run against existing database:
--   docker exec -i pg-vector-postgres-1 psql -U pgvector vla < migrations/003_questionnaires.sql

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
