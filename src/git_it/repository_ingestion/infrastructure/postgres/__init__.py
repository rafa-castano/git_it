"""PostgreSQL infrastructure adapters, split into cohesive sub-modules (batch 104).

Mirrors sqlite.py but uses psycopg (v3); all adapters use connection-per-operation
(no pooling), matching the SQLite pattern. Placeholders use %s (psycopg3 style,
not ? as in sqlite3).

This package re-exports the full public API that used to live in the single
``postgres.py`` module, so every existing ``from
git_it.repository_ingestion.infrastructure.postgres import <Class>`` import site
keeps working unchanged.
"""

from ._common import initialize
from .analysis import PostgresCaseStudyStore, PostgresCommitAnalysisStore, PostgresSynopsisStore
from .commits import (
    PostgresCommitCountReader,
    PostgresCommitReader,
    PostgresCommitStore,
    PostgresCommitWithAnalysisReader,
)
from .contributors import PostgresContributorReader
from .discussions import PostgresDiscussionEvidenceStore
from .files import PostgresFileFactReader, PostgresFileFactStore
from .github import (
    PostgresDefaultBranchStore,
    PostgresGithubContextCache,
    PostgresRepoMetadataStore,
)
from .ingestion import PostgresIngestionRunStore
from .repository import PostgresRepositoryDeleter, PostgresRepositoryListReader

__all__ = [
    "PostgresCaseStudyStore",
    "PostgresCommitAnalysisStore",
    "PostgresCommitCountReader",
    "PostgresCommitReader",
    "PostgresCommitStore",
    "PostgresCommitWithAnalysisReader",
    "PostgresContributorReader",
    "PostgresDefaultBranchStore",
    "PostgresDiscussionEvidenceStore",
    "PostgresFileFactReader",
    "PostgresFileFactStore",
    "PostgresGithubContextCache",
    "PostgresIngestionRunStore",
    "PostgresRepoMetadataStore",
    "PostgresRepositoryDeleter",
    "PostgresRepositoryListReader",
    "PostgresSynopsisStore",
    "initialize",
]
