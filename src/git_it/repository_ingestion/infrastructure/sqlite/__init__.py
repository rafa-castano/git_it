"""SQLite infrastructure adapters, split into cohesive sub-modules (batch 103).

This package re-exports the full public API that used to live in the single
``sqlite.py`` module, so every existing ``from
git_it.repository_ingestion.infrastructure.sqlite import <Class>`` import site
keeps working unchanged.
"""

from .advisories import SqliteAdvisoryEvidenceStore
from .analysis import SqliteCaseStudyStore, SqliteCommitAnalysisStore, SqliteSynopsisStore
from .commits import (
    SqliteCommitCountReader,
    SqliteCommitFactStore,
    SqliteCommitReader,
    SqliteCommitWithAnalysisReader,
    SqliteStoredCommitShaReader,
)
from .contributors import SqliteContributorReader
from .discussions import SqliteDiscussionEvidenceStore
from .embeddings import SqliteEmbeddingStore
from .file_tree import SqliteFileTreeStore
from .files import SqliteFileFactReader, SqliteFileFactStore
from .github import SqliteDefaultBranchStore, SqliteGithubContextCache, SqliteRepoMetadataStore
from .ingestion import SqliteIngestionRunStore
from .project_docs import SqliteProjectDocStore
from .releases import SqliteReleaseEvidenceStore
from .repository import SqliteRepositoryDeleter, SqliteRepositoryListReader

__all__ = [
    "SqliteAdvisoryEvidenceStore",
    "SqliteCaseStudyStore",
    "SqliteCommitAnalysisStore",
    "SqliteCommitCountReader",
    "SqliteCommitFactStore",
    "SqliteCommitReader",
    "SqliteCommitWithAnalysisReader",
    "SqliteContributorReader",
    "SqliteDefaultBranchStore",
    "SqliteDiscussionEvidenceStore",
    "SqliteEmbeddingStore",
    "SqliteFileFactReader",
    "SqliteFileFactStore",
    "SqliteFileTreeStore",
    "SqliteGithubContextCache",
    "SqliteIngestionRunStore",
    "SqliteProjectDocStore",
    "SqliteReleaseEvidenceStore",
    "SqliteRepoMetadataStore",
    "SqliteRepositoryDeleter",
    "SqliteRepositoryListReader",
    "SqliteStoredCommitShaReader",
    "SqliteSynopsisStore",
]
