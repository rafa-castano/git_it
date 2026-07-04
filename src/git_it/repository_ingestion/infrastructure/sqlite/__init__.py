"""SQLite infrastructure adapters, split into cohesive sub-modules (batch 103).

This package re-exports the full public API that used to live in the single
``sqlite.py`` module, so every existing ``from
git_it.repository_ingestion.infrastructure.sqlite import <Class>`` import site
keeps working unchanged.
"""

from .analysis import SqliteCaseStudyStore, SqliteCommitAnalysisStore, SqliteSynopsisStore
from .commits import (
    SqliteCommitCountReader,
    SqliteCommitFactStore,
    SqliteCommitReader,
    SqliteCommitWithAnalysisReader,
)
from .contributors import SqliteContributorReader
from .discussions import SqliteDiscussionEvidenceStore
from .files import SqliteFileFactReader, SqliteFileFactStore
from .github import SqliteDefaultBranchStore, SqliteGithubContextCache, SqliteRepoMetadataStore
from .ingestion import SqliteIngestionRunStore
from .repository import SqliteRepositoryDeleter, SqliteRepositoryListReader

__all__ = [
    "SqliteCaseStudyStore",
    "SqliteCommitAnalysisStore",
    "SqliteCommitCountReader",
    "SqliteCommitFactStore",
    "SqliteCommitReader",
    "SqliteCommitWithAnalysisReader",
    "SqliteContributorReader",
    "SqliteDefaultBranchStore",
    "SqliteDiscussionEvidenceStore",
    "SqliteFileFactReader",
    "SqliteFileFactStore",
    "SqliteGithubContextCache",
    "SqliteIngestionRunStore",
    "SqliteRepoMetadataStore",
    "SqliteRepositoryDeleter",
    "SqliteRepositoryListReader",
    "SqliteSynopsisStore",
]
