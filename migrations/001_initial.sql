-- Git It initial schema for PostgreSQL
-- Run this once to create all tables.
-- All statements are idempotent (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id       TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    status       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    completed_at TEXT,
    error_code   TEXT,
    error_stage  TEXT,
    retryable    INTEGER,
    safe_message TEXT
);

CREATE TABLE IF NOT EXISTS commit_facts (
    id             BIGSERIAL PRIMARY KEY,
    repository_id  TEXT NOT NULL,
    sha            TEXT NOT NULL,
    committed_at   TEXT NOT NULL,
    message        TEXT NOT NULL,
    author_name    TEXT NOT NULL,
    committer_name TEXT NOT NULL,
    parent_shas    TEXT NOT NULL,
    author_email   TEXT NOT NULL DEFAULT '',
    UNIQUE (repository_id, sha)
);

CREATE TABLE IF NOT EXISTS file_facts (
    id            BIGSERIAL PRIMARY KEY,
    repository_id TEXT NOT NULL,
    commit_sha    TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    insertions    INTEGER NOT NULL,
    deletions     INTEGER NOT NULL,
    UNIQUE (repository_id, commit_sha, file_path)
);

CREATE TABLE IF NOT EXISTS commit_analyses (
    id            BIGSERIAL PRIMARY KEY,
    repository_id TEXT NOT NULL,
    commit_sha    TEXT NOT NULL,
    data          TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
    UNIQUE (repository_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS case_studies (
    repository_id TEXT NOT NULL,
    audience      TEXT NOT NULL DEFAULT 'intermediate',
    narrative     TEXT NOT NULL,
    commit_count  INTEGER NOT NULL,
    hotspot_count INTEGER NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
    PRIMARY KEY (repository_id, audience)
);

CREATE TABLE IF NOT EXISTS repository_synopsis (
    repository_id TEXT PRIMARY KEY,
    synopsis      TEXT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS github_context (
    repository_id   TEXT NOT NULL,
    commit_sha      TEXT NOT NULL,
    pr_number       INTEGER,
    pr_title        TEXT,
    pr_body         TEXT,
    issue_numbers   TEXT NOT NULL DEFAULT '[]',
    issue_bodies    TEXT NOT NULL DEFAULT '[]',
    has_github_data INTEGER NOT NULL DEFAULT 0,
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (repository_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS repo_metadata (
    repository_id TEXT PRIMARY KEY,
    stars         INTEGER NOT NULL,
    languages     TEXT NOT NULL DEFAULT '[]',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS default_branch_metadata (
    repository_id  TEXT PRIMARY KEY,
    default_branch TEXT NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS repository_files (
    repository_id TEXT NOT NULL,
    path          TEXT NOT NULL,
    PRIMARY KEY (repository_id, path)
);

CREATE TABLE IF NOT EXISTS project_docs (
    repository_id       TEXT PRIMARY KEY,
    readme_text         TEXT,
    readme_truncated    INTEGER NOT NULL DEFAULT 0,
    changelog_text      TEXT,
    changelog_truncated INTEGER NOT NULL DEFAULT 0,
    captured_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discussion_evidence (
    repository_id  TEXT NOT NULL,
    discussion_id  TEXT NOT NULL,
    discussion_url TEXT NOT NULL,
    claim_type     TEXT NOT NULL,
    summary        TEXT NOT NULL,
    confidence     DOUBLE PRECISION NOT NULL,
    limitations    TEXT NOT NULL DEFAULT '[]',
    source_inputs  TEXT NOT NULL DEFAULT '[]',
    generated_at   TEXT NOT NULL,
    model          TEXT NOT NULL,
    PRIMARY KEY (repository_id, discussion_id)
);

CREATE TABLE IF NOT EXISTS release_evidence (
    repository_id  TEXT NOT NULL,
    tag_name       TEXT NOT NULL,
    release_url    TEXT NOT NULL,
    claim_type     TEXT NOT NULL,
    summary        TEXT NOT NULL,
    confidence     DOUBLE PRECISION NOT NULL,
    limitations    TEXT NOT NULL DEFAULT '[]',
    source_inputs  TEXT NOT NULL DEFAULT '[]',
    generated_at   TEXT NOT NULL,
    model          TEXT NOT NULL,
    PRIMARY KEY (repository_id, tag_name)
);

CREATE TABLE IF NOT EXISTS advisory_evidence (
    repository_id  TEXT NOT NULL,
    ghsa_id        TEXT NOT NULL,
    advisory_url   TEXT NOT NULL,
    severity       TEXT NOT NULL,
    summary        TEXT NOT NULL,
    confidence     DOUBLE PRECISION NOT NULL,
    limitations    TEXT NOT NULL DEFAULT '[]',
    source_inputs  TEXT NOT NULL DEFAULT '[]',
    generated_at   TEXT NOT NULL,
    model          TEXT NOT NULL,
    PRIMARY KEY (repository_id, ghsa_id)
);

CREATE TABLE IF NOT EXISTS embedding_vectors (
    repository_id TEXT NOT NULL,
    source_type   TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    text          TEXT NOT NULL,
    vector_json   TEXT NOT NULL,
    model         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (repository_id, source_type, source_id)
);
